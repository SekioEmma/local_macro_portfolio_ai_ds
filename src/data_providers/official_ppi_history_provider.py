from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from data_quality import market_history_store

from . import fred_provider


PPI_FINAL_DEMAND_CONFIG_KEY = "ppi_final_demand"
PPI_FINAL_DEMAND_METRIC_KEY = "ppi_final_demand"
PPI_FINAL_DEMAND_SERIES = "PPIFIS"


def load_official_ppi_history_config(data_sources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    package = data_sources.get("deepseek_market_data_package")
    if not isinstance(package, dict):
        return {}
    inflation_config = package.get("inflation_indicators")
    if not isinstance(inflation_config, dict):
        return {}
    item = inflation_config.get(PPI_FINAL_DEMAND_CONFIG_KEY)
    if not isinstance(item, dict):
        return {}
    provider = str(item.get("provider") or "").strip().lower()
    series_id = str(item.get("series_id") or "").strip()
    if provider != "fred" or series_id != PPI_FINAL_DEMAND_SERIES:
        return {}
    return {
        PPI_FINAL_DEMAND_METRIC_KEY: {
            "metric_key": PPI_FINAL_DEMAND_METRIC_KEY,
            "source_key": PPI_FINAL_DEMAND_CONFIG_KEY,
            "provider": "fred",
            "series_id": series_id,
            "name": item.get("name") or "Producer Price Index by Commodity: Final Demand",
            "unit": item.get("unit") or "index",
            "frequency": item.get("frequency") or "monthly",
            "source_tier": item.get("source_tier") or "official_or_public_data_api",
            "interpretation_hint": item.get("interpretation_hint"),
        }
    }


def fetch_official_ppi_history(
    config: dict[str, dict[str, Any]],
    *,
    limit: int = 180,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_fetcher = fetcher or fred_provider.get_fred_series
    fetched_at = _utc_now()
    raw_data: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for metric_key, item in sorted(config.items()):
        series_id = str(item.get("series_id") or "").strip()
        if series_id != PPI_FINAL_DEMAND_SERIES:
            errors.append({"metric_key": metric_key, "error": "PPIFIS series_id required"})
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


def normalize_official_ppi_history(
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
        if series_id != PPI_FINAL_DEMAND_SERIES:
            errors.append({"metric_key": metric_key, "error": "series_id is not PPIFIS"})
            continue
        for observation in payload.get("data", []):
            value = _to_float_or_none(observation.get("value"))
            observation_date = _text_or_none(observation.get("date"))
            if value is None or observation_date is None:
                continue
            records.append(
                {
                    "metric_key": PPI_FINAL_DEMAND_METRIC_KEY,
                    "observation_date": observation_date,
                    "value": value,
                    "unit": item_config.get("unit") or "index",
                    "source": "FRED",
                    "provider": "FRED",
                    "source_series": PPI_FINAL_DEMAND_SERIES,
                    "fetched_at": fetched_at,
                    "generated_at": payload.get("timestamp") or fetched_at,
                    "name": item_config.get("name"),
                    "interpretation_hint": item_config.get("interpretation_hint"),
                }
            )
    records.sort(key=lambda item: (item["metric_key"], item["observation_date"]))
    return {"records": records, "errors": errors}


def build_market_observations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in records:
        observations.append(
            {
                "metric_key": PPI_FINAL_DEMAND_METRIC_KEY,
                "observation_date": record["observation_date"],
                "value": record["value"],
                "value_text": str(record["value"]),
                "unit": record.get("unit") or "index",
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "provider": "FRED",
                "source_series": PPI_FINAL_DEMAND_SERIES,
                "generated_at": record.get("generated_at"),
                "fetched_at": record.get("fetched_at"),
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": {
                    "provider": "FRED",
                    "source_series": PPI_FINAL_DEMAND_SERIES,
                    "source_detail": (
                        "Headline PPI Final Demand index relayed by FRED; distinct from PPIACO."
                    ),
                },
            }
        )
    return observations


def upsert_official_ppi_history(
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
