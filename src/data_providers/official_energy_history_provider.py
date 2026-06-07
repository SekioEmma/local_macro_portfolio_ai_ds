from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from data_quality import market_history_store

from . import fred_provider


ENERGY_HISTORY_CONFIG_KEYS = {
    "wti_oil": "wti",
    "brent_oil": "brent",
}
OFFICIAL_OIL_SERIES = {"DCOILWTICO", "DCOILBRENTEU"}


def load_official_energy_history_config(data_sources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    package = data_sources.get("deepseek_market_data_package")
    if not isinstance(package, dict):
        return {}
    oil_config = package.get("oil_and_energy")
    if not isinstance(oil_config, dict):
        return {}

    result: dict[str, dict[str, Any]] = {}
    for source_key, metric_key in ENERGY_HISTORY_CONFIG_KEYS.items():
        item = oil_config.get(source_key)
        if not isinstance(item, dict):
            continue
        series_id = str(item.get("series_id") or "").strip()
        provider = str(item.get("provider") or "").strip().lower()
        if provider != "fred" or not series_id:
            continue
        result[metric_key] = {
            "metric_key": metric_key,
            "source_key": source_key,
            "provider": "fred",
            "series_id": series_id,
            "name": item.get("name") or source_key,
            "unit": item.get("unit") or "USD per barrel",
            "source_tier": item.get("source_tier") or "official_or_public_data_api",
            "interpretation_hint": item.get("interpretation_hint"),
        }
    return result


def fetch_official_energy_history(
    config: dict[str, dict[str, Any]],
    *,
    limit: int = 370,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_fetcher = fetcher or fred_provider.get_fred_series
    fetched_at = _utc_now()
    raw_data: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for metric_key, item in sorted(config.items()):
        series_id = str(item.get("series_id") or "").strip()
        if not series_id:
            errors.append({"metric_key": metric_key, "error": "series_id missing"})
            continue
        result = active_fetcher(series_id, limit)
        raw_data[metric_key] = result
        if result.get("status") != "ok":
            errors.append(
                {
                    "metric_key": metric_key,
                    "series_id": series_id,
                    "error": str(result.get("error") or "FRED history fetch failed"),
                }
            )
    return {
        "status": "ok" if not errors else "partial_error" if raw_data else "error",
        "generated_at": fetched_at,
        "raw_data": raw_data,
        "errors": errors,
    }


def normalize_official_energy_history(
    raw_data: dict[str, dict[str, Any]],
    config: dict[str, dict[str, Any]],
    *,
    fetched_at: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for metric_key, payload in sorted(raw_data.items()):
        item_config = config.get(metric_key)
        if not isinstance(item_config, dict):
            errors.append({"metric_key": metric_key, "error": "config missing"})
            continue
        if payload.get("status") != "ok":
            errors.append(
                {
                    "metric_key": metric_key,
                    "error": str(payload.get("error") or "history status not ok"),
                }
            )
            continue
        series_id = str(payload.get("series_id") or item_config.get("series_id") or "").strip()
        for observation in payload.get("data", []):
            value = _to_float_or_none(observation.get("value"))
            observation_date = _text_or_none(observation.get("date"))
            if value is None or observation_date is None:
                continue
            records.append(
                {
                    "metric_key": metric_key,
                    "observation_date": observation_date,
                    "value": value,
                    "unit": item_config.get("unit") or "USD per barrel",
                    "source": f"FRED:{series_id}",
                    "provider": "FRED",
                    "source_series": series_id,
                    "fetched_at": fetched_at,
                    "generated_at": payload.get("timestamp") or fetched_at,
                    "name": item_config.get("name"),
                }
            )
    records.sort(key=lambda item: (item["metric_key"], item["observation_date"]))
    return {"records": records, "errors": errors}


def build_market_observations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in records:
        series_id = str(record["source_series"])
        observations.append(
            {
                "metric_key": record["metric_key"],
                "observation_date": record["observation_date"],
                "value": record["value"],
                "value_text": str(record["value"]),
                "unit": record.get("unit") or "USD per barrel",
                "status": "ok",
                "source": record["source"],
                "source_badge": "official",
                "provider": "FRED",
                "source_series": series_id,
                "generated_at": record.get("generated_at"),
                "fetched_at": record.get("fetched_at"),
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": {
                    "provider": "FRED",
                    "source_series": series_id,
                    "source_detail": "EIA daily crude oil price series distributed through FRED",
                },
            }
        )
    return observations


def upsert_official_energy_history(
    observations: list[dict[str, Any]],
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    summary = {"inserted_count": 0, "updated_count": 0, "skipped_count": 0, "skipped_reasons": {}}
    for observation in observations:
        try:
            result = market_history_store.upsert_market_observation(observation, db_path=db_path)
        except market_history_store.MarketHistoryValidationError as exc:
            _record_skip(summary, str(exc))
            continue
        if result["status"] == "inserted":
            summary["inserted_count"] += 1
        elif result["status"] == "updated":
            summary["updated_count"] += 1
    return summary


def _record_skip(summary: dict[str, Any], reason: str) -> None:
    key = reason or "not_eligible"
    summary["skipped_count"] += 1
    summary["skipped_reasons"][key] = summary["skipped_reasons"].get(key, 0) + 1


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
