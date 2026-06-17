from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "data_sources.yaml"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import fred_provider, market_data_service  # noqa: E402
from data_providers import market_history_store  # noqa: E402


LABOR_SERIES: dict[str, dict[str, str]] = {
    "unemployment_rate": {
        "series_id": "UNRATE",
        "unit": "percent",
        "frequency": "monthly",
    },
    "initial_jobless_claims": {
        "series_id": "ICSA",
        "unit": "claims",
        "frequency": "weekly",
    },
    "nonfarm_payrolls": {
        "series_id": "PAYEMS",
        "unit": "thousand persons",
        "frequency": "monthly",
    },
    "continuing_claims": {
        "series_id": "CCSA",
        "unit": "claims",
        "frequency": "weekly",
    },
}
DEFAULT_MONTHLY_LIMIT = 24
DEFAULT_WEEKLY_LIMIT = 52


def build_ingest_summary(
    *,
    config_path: Path | str | None = None,
    db_path: Path | str | None = None,
    monthly_limit: int = DEFAULT_MONTHLY_LIMIT,
    weekly_limit: int = DEFAULT_WEEKLY_LIMIT,
    limit: int | None = None,
    dry_run: bool = True,
    live: bool = False,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data_sources = market_data_service.load_data_source_config(str(config_path or DEFAULT_CONFIG_PATH))
    config = load_official_labor_history_config(data_sources)
    metric_keys = sorted(config)
    limits_by_metric = {
        key: _limit_for_metric(config[key], monthly_limit=monthly_limit, weekly_limit=weekly_limit, override=limit)
        for key in metric_keys
    }
    summary: dict[str, Any] = {
        "configured_metrics": len(config),
        "enabled_metrics": metric_keys,
        "fetched_metrics": 0,
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "source_badge_distribution": {},
        "source_series_distribution": {},
        "dry_run": dry_run,
        "live": live,
        "monthly_limit": monthly_limit,
        "weekly_limit": weekly_limit,
        "limit_override": limit,
        "limits_by_metric": limits_by_metric,
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
    }
    if not live:
        summary["skipped_count"] = len(metric_keys)
        summary["skipped_reasons"]["live_disabled"] = len(metric_keys)
        return summary

    fetched = fetch_official_labor_history(
        config,
        limits_by_metric=limits_by_metric,
        fetcher=fetcher,
    )
    summary["fetched_metrics"] = len(fetched.get("raw_data", {}))
    for error in fetched.get("errors", []):
        _record_skip(summary, f"fetch_error:{error.get('metric_key')}")

    normalized = normalize_official_labor_history(
        fetched.get("raw_data", {}),
        config,
        fetched_at=fetched.get("generated_at"),
    )
    records = normalized["records"]
    summary["normalized_observations"] = len(records)
    for error in normalized["errors"]:
        _record_skip(summary, f"normalize_error:{error.get('metric_key')}")

    observations = build_market_observations(records)
    for observation in observations:
        badge = str(observation["source_badge"])
        series = str(observation["source_series"])
        summary["source_badge_distribution"][badge] = (
            summary["source_badge_distribution"].get(badge, 0) + 1
        )
        summary["source_series_distribution"][series] = (
            summary["source_series_distribution"].get(series, 0) + 1
        )
        if dry_run:
            continue
        try:
            result = market_history_store.upsert_market_observation(
                observation,
                db_path=db_path,
            )
        except market_history_store.MarketHistoryValidationError as exc:
            _record_skip(summary, str(exc))
            continue
        if result["status"] == "inserted":
            summary["inserted_count"] += 1
        elif result["status"] == "updated":
            summary["updated_count"] += 1
    return summary


def load_official_labor_history_config(data_sources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    package = data_sources.get("deepseek_market_data_package")
    if not isinstance(package, dict):
        return {}
    labor_config = package.get("labor_indicators")
    if not isinstance(labor_config, dict):
        return {}
    config: dict[str, dict[str, Any]] = {}
    for metric_key, expected in LABOR_SERIES.items():
        item = labor_config.get(metric_key)
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip().lower()
        series_id = str(item.get("series_id") or "").strip().upper()
        if provider != "fred" or series_id != expected["series_id"]:
            continue
        config[metric_key] = {
            "metric_key": metric_key,
            "provider": "fred",
            "series_id": expected["series_id"],
            "name": item.get("name") or metric_key,
            "unit": item.get("unit") or expected["unit"],
            "frequency": item.get("frequency") or expected["frequency"],
            "source_tier": item.get("source_tier") or "official_or_public_data_api",
            "interpretation_hint": item.get("interpretation_hint"),
        }
    return config


def fetch_official_labor_history(
    config: dict[str, dict[str, Any]],
    *,
    limits_by_metric: dict[str, int],
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_fetcher = fetcher or fred_provider.get_fred_series
    fetched_at = _utc_now()
    raw_data: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for metric_key, item in sorted(config.items()):
        series_id = str(item.get("series_id") or "").strip().upper()
        expected_series = LABOR_SERIES.get(metric_key, {}).get("series_id")
        if series_id != expected_series:
            errors.append({"metric_key": metric_key, "series_id": series_id, "error": "unexpected labor series_id"})
            continue
        result = active_fetcher(series_id, limits_by_metric.get(metric_key, DEFAULT_WEEKLY_LIMIT))
        raw_data[metric_key] = result
        if result.get("status") != "ok":
            errors.append(
                {
                    "metric_key": metric_key,
                    "series_id": series_id,
                    "error": str(result.get("error") or "FRED labor history fetch failed"),
                }
            )
    return {
        "status": "ok" if not errors else "partial_error" if raw_data else "error",
        "generated_at": fetched_at,
        "raw_data": raw_data,
        "errors": errors,
    }


def normalize_official_labor_history(
    raw_data: dict[str, dict[str, Any]],
    config: dict[str, dict[str, Any]],
    *,
    fetched_at: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for metric_key, payload in sorted(raw_data.items()):
        item_config = config.get(metric_key)
        expected = LABOR_SERIES.get(metric_key)
        if not isinstance(item_config, dict) or expected is None:
            errors.append({"metric_key": metric_key, "error": "config missing"})
            continue
        if payload.get("status") != "ok":
            errors.append({"metric_key": metric_key, "error": str(payload.get("error") or "history status not ok")})
            continue
        series_id = str(payload.get("series_id") or item_config.get("series_id") or "").strip().upper()
        if series_id != expected["series_id"]:
            errors.append({"metric_key": metric_key, "error": f"series_id is not {expected['series_id']}"})
            continue
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
                    "unit": item_config.get("unit") or expected["unit"],
                    "source": "FRED",
                    "provider": "FRED",
                    "source_series": expected["series_id"],
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
        series = str(record["source_series"])
        observations.append(
            {
                "metric_key": record["metric_key"],
                "observation_date": record["observation_date"],
                "value": record["value"],
                "value_text": str(record["value"]),
                "unit": record.get("unit") or LABOR_SERIES[record["metric_key"]]["unit"],
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "provider": "FRED",
                "source_series": series,
                "generated_at": record.get("generated_at"),
                "fetched_at": record.get("fetched_at"),
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": {
                    "provider": "FRED",
                    "source_series": series,
                    "source_detail": "Official labor-market history observation normalized for market_history.",
                },
            }
        )
    return observations


def _limit_for_metric(
    item: dict[str, Any],
    *,
    monthly_limit: int,
    weekly_limit: int,
    override: int | None,
) -> int:
    if override is not None:
        return override
    return weekly_limit if str(item.get("frequency") or "").lower() == "weekly" else monthly_limit


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or ingest official FRED labor history into market_history."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    parser.add_argument("--write", action="store_true", help="Write normalized observations.")
    parser.add_argument("--live", action="store_true", help="Allow live FRED download.")
    parser.add_argument("--monthly-limit", type=int, default=DEFAULT_MONTHLY_LIMIT, help="Monthly labor observation limit.")
    parser.add_argument("--weekly-limit", type=int, default=DEFAULT_WEEKLY_LIMIT, help="Weekly labor observation limit.")
    parser.add_argument("--limit", type=int, default=None, help="Override all per-series limits.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True
    summary = build_ingest_summary(
        config_path=args.config,
        db_path=args.db_path,
        monthly_limit=args.monthly_limit,
        weekly_limit=args.weekly_limit,
        limit=args.limit,
        dry_run=dry_run,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
