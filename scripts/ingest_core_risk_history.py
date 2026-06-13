from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "data_sources.yaml"
DEFAULT_YFINANCE_CONFIG_PATH = PROJECT_ROOT / "configs" / "yfinance_history.yaml"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import fred_provider, market_data_service, yfinance_history_provider  # noqa: E402
from data_quality import market_history_store  # noqa: E402


DEFAULT_FRED_LIMIT = 1600
DEFAULT_YFINANCE_PERIOD = "6y"
CORE_SOURCE_METRICS = {
    "high_yield_spread",
    "investment_grade_spread",
    "vix",
    "dgs30",
    "dfii10",
    "sp500",
    "nasdaq100",
    "initial_jobless_claims",
    "continuing_claims",
}
DERIVED_OUTPUT_METRICS = {
    "sp500_drawdown_3m",
    "nasdaq100_drawdown_3m",
    "initial_claims_4w_avg",
    "continuing_claims_4w_avg",
}


def build_ingest_summary(
    *,
    config_path: Path | str | None = None,
    yfinance_config_path: Path | str | None = None,
    db_path: Path | str | None = None,
    dry_run: bool = True,
    live: bool = False,
    metric: str | None = None,
    fred_limit: int = DEFAULT_FRED_LIMIT,
    yfinance_period: str = DEFAULT_YFINANCE_PERIOD,
    fred_fetcher: Callable[[str, int], dict[str, Any]] | None = None,
    yfinance_downloader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    data_sources = market_data_service.load_data_source_config(str(config_path or DEFAULT_CONFIG_PATH))
    official_mappings, missing_mappings = load_official_mappings(data_sources)
    yfinance_mappings = load_yfinance_core_mappings(yfinance_config_path or DEFAULT_YFINANCE_CONFIG_PATH)
    selected_metric = metric.strip() if metric else None
    official_mappings = _filter_mapping(official_mappings, selected_metric)
    yfinance_mappings = _filter_mapping(yfinance_mappings, selected_metric)
    selected_derived = sorted(
        key for key in DERIVED_OUTPUT_METRICS if selected_metric in {None, key}
    )
    if selected_metric and not official_mappings and not yfinance_mappings and not selected_derived:
        missing_mappings = sorted(set(missing_mappings + [selected_metric]))

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "live": live,
        "write": not dry_run,
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
        "planned_official_series": official_mappings,
        "planned_proxy_unofficial_series": yfinance_mappings,
        "planned_derived_historical_materialization": selected_derived,
        "missing_source_mappings": missing_mappings,
        "required_flags_for_fetch": "--live",
        "required_flags_for_write": "--live --write",
        "fetched_official_series": 0,
        "fetched_yfinance_symbols": 0,
        "normalized_raw_observations": 0,
        "derived_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "source_badge_distribution": {},
        "provider_status": {},
    }
    if not live:
        _record_skip(summary, "live_disabled", len(official_mappings) + len(yfinance_mappings))
        return summary

    raw_observations = []
    official_records = fetch_and_normalize_official(
        official_mappings,
        limit=fred_limit,
        fetcher=fred_fetcher,
    )
    summary["fetched_official_series"] = official_records["fetched_series"]
    summary["provider_status"].update(official_records["provider_status"])
    raw_observations.extend(official_records["observations"])
    for error in official_records["errors"]:
        _record_skip(summary, error)

    yfinance_records = fetch_and_normalize_yfinance(
        yfinance_mappings,
        period=yfinance_period,
        downloader=yfinance_downloader,
    )
    summary["fetched_yfinance_symbols"] = yfinance_records["fetched_symbols"]
    summary["provider_status"].update(yfinance_records["provider_status"])
    raw_observations.extend(yfinance_records["observations"])
    for error in yfinance_records["errors"]:
        _record_skip(summary, error)

    summary["normalized_raw_observations"] = len(raw_observations)
    for observation in raw_observations:
        _count_badge(summary, observation["source_badge"])
        if dry_run:
            continue
        _write_observation(summary, observation, db_path=db_path)

    if not dry_run:
        derived = build_derived_history_observations(
            metrics=selected_derived,
            db_path=db_path,
        )
        summary["derived_observations"] = len(derived)
        for observation in derived:
            _count_badge(summary, observation["source_badge"])
            _write_observation(summary, observation, db_path=db_path)
    return summary


def load_official_mappings(data_sources: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    mappings: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    fred_series = data_sources.get("fred_series") if isinstance(data_sources, dict) else {}
    financial_conditions = data_sources.get("financial_conditions") if isinstance(data_sources, dict) else {}
    labor = (
        data_sources.get("deepseek_market_data_package", {})
        .get("labor_indicators", {})
        if isinstance(data_sources.get("deepseek_market_data_package"), dict)
        else {}
    )
    candidates = {
        "dgs30": ("dgs30", fred_series, "official"),
        "dfii10": ("real_yield_10y", financial_conditions, "official"),
        "high_yield_spread": ("high_yield_spread", financial_conditions, "official_fallback"),
        "investment_grade_spread": ("investment_grade_spread", financial_conditions, "official_fallback"),
        "vix": ("vix", financial_conditions, "official_fallback"),
        "initial_jobless_claims": ("initial_jobless_claims", labor, "official"),
        "continuing_claims": ("continuing_claims", labor, "official"),
    }
    for metric_key, (config_key, section, source_badge) in candidates.items():
        item = section.get(config_key) if isinstance(section, dict) else None
        if not isinstance(item, dict) or str(item.get("provider") or "fred").lower() != "fred":
            missing.append(metric_key)
            continue
        series_id = str(item.get("series_id") or "").strip().upper()
        if not series_id:
            missing.append(metric_key)
            continue
        mappings[metric_key] = {
            "metric_key": metric_key,
            "provider": "FRED",
            "series_id": series_id,
            "source": "FRED",
            "source_badge": source_badge,
            "unit": item.get("unit") or "percent",
            "name": item.get("name") or metric_key,
        }
    return mappings, sorted(missing)


def load_yfinance_core_mappings(path: Path | str) -> dict[str, dict[str, Any]]:
    config = yfinance_history_provider.load_yfinance_history_config(path)
    allowed = {"sp500", "nasdaq100"}
    return {
        symbol: item
        for symbol, item in config.items()
        if item.get("metric_key") in allowed
        and item.get("source_badge") in {"unofficial_fallback", "proxy"}
    }


def fetch_and_normalize_official(
    mappings: dict[str, dict[str, Any]],
    *,
    limit: int,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_fetcher = fetcher or fred_provider.get_fred_series
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    provider_status: dict[str, str] = {}
    fetched_at = _utc_now()
    for metric_key, item in sorted(mappings.items()):
        payload = active_fetcher(item["series_id"], limit)
        provider_status[metric_key] = str(payload.get("status") or "unknown")
        if payload.get("status") != "ok":
            errors.append(f"fetch_error:{metric_key}")
            continue
        for row in payload.get("data", []):
            value = _to_float_or_none(row.get("value"))
            observation_date = _text_or_none(row.get("date"))
            if value is None or observation_date is None:
                continue
            observations.append(
                {
                    "metric_key": metric_key,
                    "observation_date": observation_date,
                    "value": value,
                    "value_text": str(value),
                    "unit": item.get("unit"),
                    "status": "ok",
                    "source": item.get("source") or "FRED",
                    "source_badge": item["source_badge"],
                    "provider": "FRED",
                    "source_series": item["series_id"],
                    "generated_at": payload.get("timestamp") or fetched_at,
                    "fetched_at": fetched_at,
                    "freshness_status": "historical",
                    "ai_context_allowed": item["source_badge"] in {"official", "official_fallback"},
                    "metric_kind": "raw",
                    "lineage": {
                        "provider": "FRED",
                        "source_series": item["series_id"],
                        "source_detail": "Core risk history backfill normalized observation.",
                    },
                }
            )
    return {
        "fetched_series": len(mappings),
        "observations": observations,
        "errors": errors,
        "provider_status": provider_status,
    }


def fetch_and_normalize_yfinance(
    mappings: dict[str, dict[str, Any]],
    *,
    period: str,
    downloader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not mappings:
        return {"fetched_symbols": 0, "observations": [], "errors": [], "provider_status": {}}
    symbols = sorted(mappings)
    fetched = yfinance_history_provider.fetch_yfinance_batch_history(
        symbols,
        period=period,
        interval="1d",
        downloader=downloader,
    )
    provider_status = {symbol: str(fetched.get("status") or "unknown") for symbol in symbols}
    if fetched.get("status") != "ok":
        return {
            "fetched_symbols": len(symbols),
            "observations": [],
            "errors": [f"fetch_error:{symbol}" for symbol in symbols],
            "provider_status": provider_status,
        }
    normalized = yfinance_history_provider.normalize_yfinance_history(
        fetched.get("raw_data"),
        mappings,
        fetched_at=fetched.get("generated_at"),
    )
    observations = yfinance_history_provider.build_market_observations_from_yfinance(
        normalized["records"]
    )
    return {
        "fetched_symbols": len(symbols),
        "observations": observations,
        "errors": [f"normalize_error:{item['symbol']}" for item in normalized["errors"]],
        "provider_status": provider_status,
    }


def build_derived_history_observations(
    *,
    metrics: list[str] | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    requested = set(metrics or DERIVED_OUTPUT_METRICS)
    observations: list[dict[str, Any]] = []
    if "sp500_drawdown_3m" in requested:
        observations.extend(_drawdown_observations("sp500", "sp500_drawdown_3m", 90, db_path=db_path))
    if "nasdaq100_drawdown_3m" in requested:
        observations.extend(_drawdown_observations("nasdaq100", "nasdaq100_drawdown_3m", 90, db_path=db_path))
    if "initial_claims_4w_avg" in requested:
        observations.extend(_rolling_average_observations("initial_jobless_claims", "initial_claims_4w_avg", 4, "claims", db_path=db_path))
    if "continuing_claims_4w_avg" in requested:
        observations.extend(_rolling_average_observations("continuing_claims", "continuing_claims_4w_avg", 4, "claims", db_path=db_path))
    return observations


def _drawdown_observations(
    source_metric: str,
    output_metric: str,
    window_days: int,
    *,
    db_path: Path | str | None,
) -> list[dict[str, Any]]:
    rows = _numeric_history(source_metric, db_path=db_path)
    observations: list[dict[str, Any]] = []
    for index, latest in enumerate(rows):
        window_start = latest["date"] - timedelta(days=window_days)
        window = [row for row in rows[: index + 1] if row["date"] >= window_start]
        if len(window) < 2:
            continue
        peak = max(row["value"] for row in window)
        if peak == 0:
            continue
        value = latest["value"] / peak - 1.0
        observations.append(_derived_observation(output_metric, latest, value, "percent", [source_metric], f"{window_days}D rolling drawdown"))
    return observations


def _rolling_average_observations(
    source_metric: str,
    output_metric: str,
    window_observations: int,
    unit: str,
    *,
    db_path: Path | str | None,
) -> list[dict[str, Any]]:
    rows = _numeric_history(source_metric, db_path=db_path)
    observations: list[dict[str, Any]] = []
    for index in range(window_observations - 1, len(rows)):
        window = rows[index - window_observations + 1 : index + 1]
        latest = window[-1]
        value = sum(row["value"] for row in window) / window_observations
        observations.append(_derived_observation(output_metric, latest, value, unit, [source_metric], f"{window_observations} observation rolling average"))
    return observations


def _derived_observation(
    metric_key: str,
    latest: dict[str, Any],
    value: float,
    unit: str,
    dependency_keys: list[str],
    calculation: str,
) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "observation_date": latest["observation_date"],
        "value": value,
        "value_text": f"{value:.6g}",
        "unit": unit,
        "status": "ok",
        "source": "local_market_history",
        "source_badge": "derived",
        "provider": "local_market_history",
        "source_series": ",".join(dependency_keys),
        "generated_at": _utc_now(),
        "fetched_at": _utc_now(),
        "freshness_status": "historical",
        "ai_context_allowed": False,
        "metric_kind": "derived",
        "lineage": {
            "calculation": calculation,
            "dependency_keys": dependency_keys,
            "dependency_source_badge": latest.get("source_badge"),
            "dependency_source_series": latest.get("source_series"),
            "dependency_observation_date": latest.get("observation_date"),
        },
    }


def _numeric_history(metric_key: str, *, db_path: Path | str | None) -> list[dict[str, Any]]:
    rows = market_history_store.list_market_observations(
        metric_key=metric_key,
        limit=market_history_store.MAX_LIMIT,
        db_path=db_path,
    )
    result: list[dict[str, Any]] = []
    for row in reversed(rows):
        value = _to_float_or_none(row.get("value_numeric"))
        parsed_date = _parse_date(row.get("observation_date"))
        if value is None or parsed_date is None:
            continue
        if row.get("status") in market_history_store.BLOCKED_STATUSES:
            continue
        result.append({**row, "value": value, "date": parsed_date})
    return result


def _write_observation(
    summary: dict[str, Any],
    observation: dict[str, Any],
    *,
    db_path: Path | str | None,
) -> None:
    try:
        result = market_history_store.upsert_market_observation(observation, db_path=db_path)
    except market_history_store.MarketHistoryValidationError as exc:
        _record_skip(summary, str(exc))
        return
    if result["status"] == "inserted":
        summary["inserted_count"] += 1
    elif result["status"] == "updated":
        summary["updated_count"] += 1


def _filter_mapping(
    mapping: dict[str, dict[str, Any]],
    metric: str | None,
) -> dict[str, dict[str, Any]]:
    if metric is None:
        return mapping
    return {
        key: item
        for key, item in mapping.items()
        if key == metric or item.get("metric_key") == metric
    }


def _record_skip(summary: dict[str, Any], reason: str, count: int = 1) -> None:
    if count <= 0:
        return
    summary["skipped_count"] += count
    summary["skipped_reasons"][reason] = summary["skipped_reasons"].get(reason, 0) + count


def _count_badge(summary: dict[str, Any], badge: str) -> None:
    summary["source_badge_distribution"][badge] = summary["source_badge_distribution"].get(badge, 0) + 1


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


def _parse_date(value: Any):
    from datetime import date

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or backfill core D13 risk history into local market_history."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without fetching or writing.")
    parser.add_argument("--live", action="store_true", help="Allow live provider fetch.")
    parser.add_argument("--write", action="store_true", help="Write normalized observations.")
    parser.add_argument("--metric", default=None, help="Optional source or derived metric key.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--yfinance-config", type=Path, default=DEFAULT_YFINANCE_CONFIG_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--fred-limit", type=int, default=DEFAULT_FRED_LIMIT)
    parser.add_argument("--yfinance-period", default=DEFAULT_YFINANCE_PERIOD)
    args = parser.parse_args(argv)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True
    summary = build_ingest_summary(
        config_path=args.config,
        yfinance_config_path=args.yfinance_config,
        db_path=args.db_path,
        dry_run=dry_run,
        live=args.live,
        metric=args.metric,
        fred_limit=args.fred_limit,
        yfinance_period=args.yfinance_period,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
