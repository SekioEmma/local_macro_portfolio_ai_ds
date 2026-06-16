from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_quality import historical_validation, market_history_store  # noqa: E402


TARGET_METRICS = {
    "high_yield_spread": {
        "series_id": "BAMLH0A0HYM2",
        "aliases": ("hy_oas", "high_yield_oas", "credit_spread_hy"),
    },
    "investment_grade_spread": {
        "series_id": "BAMLC0A0CM",
        "aliases": ("ig_oas", "investment_grade_oas", "credit_spread_ig"),
    },
}
PROVIDER_SERIES = ("BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y")
DEFAULT_TABLE_CANDIDATES = ("market_observations", "observations", "metric_history")
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
MINIMUM_OBSERVATION_COUNT = 60
THREE_YEAR_DAYS = 365 * 3
FIVE_YEAR_DAYS = 365 * 5
TEN_YEAR_DAYS = 365 * 10
LONG_HISTORY_DAYS = 365 * 20
EVENT_WINDOWS = (
    ("dotcom_2000_2002", date(2000, 1, 1), date(2002, 12, 31)),
    ("global_financial_crisis_2008", date(2008, 1, 1), date(2009, 6, 30)),
    ("eurozone_us_downgrade_2011", date(2011, 7, 1), date(2011, 12, 31)),
    ("credit_energy_2015_2016", date(2015, 7, 1), date(2016, 3, 31)),
    ("q4_2018_tightening", date(2018, 10, 1), date(2018, 12, 31)),
    ("covid_liquidity_2020", date(2020, 2, 1), date(2020, 5, 31)),
    ("inflation_rates_2022", date(2022, 1, 1), date(2022, 12, 31)),
    ("regional_bank_2023", date(2023, 3, 1), date(2023, 5, 31)),
)


@dataclass(frozen=True)
class TableSchema:
    table_name: str
    columns: set[str]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    include_provider = bool(args.probe_fred_range)
    result = run_audit(
        market_history_db=args.market_history_db,
        include_provider_probe=include_provider,
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_text(result))
    return 0


def run_audit(
    *,
    market_history_db: Path | str | None = None,
    include_provider_probe: bool = False,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    db_path = Path(market_history_db) if market_history_db else market_history_store.get_default_market_history_db_path()
    local = audit_local_market_history(db_path)
    provider = (
        audit_fred_provider_ranges(timeout_seconds=timeout_seconds)
        if include_provider_probe
        else {}
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "probe_fred_range" if include_provider_probe else "local_only",
        "safety": {
            "reads_local_market_history_only": not include_provider_probe,
            "writes_database": False,
            "writes_csv": False,
            "emits_raw_series": False,
            "reads_dotenv": False,
            "api_key_source": "process_environment_only",
        },
        "local_market_history": local,
        "fred_provider_availability": provider,
        "d13_eligibility": _d13_eligibility(local, provider),
        "d19_historical_validation_impact": _d19_impact(local),
        "license_reproducibility_boundary": _license_boundary(provider),
    }


def audit_local_market_history(db_path: Path | str) -> dict[str, Any]:
    path = Path(db_path)
    result: dict[str, Any] = {
        "db_path": _safe_path_label(path),
        "db_exists": path.exists(),
        "schema": {"table": None, "compatible": False, "notes": []},
        "metrics": {},
    }
    if not path.exists():
        result["schema"]["notes"].append("market_history_db_missing")
        for metric_key in TARGET_METRICS:
            result["metrics"][metric_key] = _empty_local_metric(metric_key, "no_local_history")
        return result

    try:
        with _connect_read_only(path) as connection:
            schema = _find_compatible_table(connection)
            if schema is None:
                result["schema"]["notes"].append("no_compatible_market_history_table")
                for metric_key in TARGET_METRICS:
                    result["metrics"][metric_key] = _empty_local_metric(metric_key, "schema_not_supported")
                return result
            result["schema"] = {
                "table": schema.table_name,
                "compatible": True,
                "columns_detected": sorted(schema.columns),
                "notes": ["read_only_sqlite_mode"],
            }
            for metric_key, spec in TARGET_METRICS.items():
                result["metrics"][metric_key] = _local_metric_summary(
                    connection,
                    schema,
                    metric_key,
                    spec["series_id"],
                    tuple(spec["aliases"]),
                )
    except sqlite3.Error as exc:
        result["schema"]["notes"].append(f"sqlite_error:{type(exc).__name__}")
        for metric_key in TARGET_METRICS:
            result["metrics"][metric_key] = _empty_local_metric(metric_key, "sqlite_read_failed")
    return result


def audit_fred_provider_ranges(*, timeout_seconds: int = 20) -> dict[str, Any]:
    return {
        series_id: _probe_fred_series_range(series_id, timeout_seconds=timeout_seconds)
        for series_id in PROVIDER_SERIES
    }


def _local_metric_summary(
    connection: sqlite3.Connection,
    schema: TableSchema,
    metric_key: str,
    series_id: str,
    aliases: tuple[str, ...],
) -> dict[str, Any]:
    rows = _read_metric_rows(connection, schema, metric_key)
    matched_by = "metric_key"
    if not rows:
        for alias in aliases:
            rows = _read_metric_rows(connection, schema, alias)
            if rows:
                matched_by = f"alias:{alias}"
                break
    if not rows and "source_series" in schema.columns:
        rows = _read_source_series_rows(connection, schema, series_id)
        if rows:
            matched_by = f"source_series:{series_id}"
    if not rows:
        return _empty_local_metric(metric_key, "no_local_history")

    numeric_rows = [
        row
        for row in rows
        if row.get("observation_date") and _to_float_or_none(row.get("value_numeric")) is not None
    ]
    parsed_dates = sorted(
        {
            parsed
            for row in numeric_rows
            for parsed in [_parse_date(row.get("observation_date"))]
            if parsed is not None
        }
    )
    start = parsed_dates[0] if parsed_dates else None
    end = parsed_dates[-1] if parsed_dates else None
    gaps = _gap_summary(parsed_dates)
    duplicate_summary = _duplicate_summary(rows)
    span_days = (end - start).days if start and end else 0
    non_null_count = len(numeric_rows)
    return {
        "metric_key": metric_key,
        "series_id": series_id,
        "matched_by": matched_by,
        "local_start": start.isoformat() if start else None,
        "local_end": end.isoformat() if end else None,
        "local_non_null_count": non_null_count,
        "local_row_count": len(rows),
        "local_null_count": len(rows) - non_null_count,
        "local_distinct_date_count": len(parsed_dates),
        "local_coverage_days": span_days,
        "local_coverage_years": round(span_days / 365.25, 3) if span_days else 0.0,
        "local_frequency_guess": _frequency_guess(parsed_dates),
        "source_series_detected": _distinct_values(rows, "source_series"),
        "source_badges_detected": _distinct_values(rows, "source_badge"),
        "statuses_detected": _distinct_values(rows, "status"),
        "gaps": gaps,
        "duplicate_observations": duplicate_summary,
        "abnormal_null_count": len(rows) - non_null_count,
        "coverage_status": _coverage_status(span_days, non_null_count),
    }


def _read_metric_rows(
    connection: sqlite3.Connection,
    schema: TableSchema,
    metric_key: str,
) -> list[dict[str, Any]]:
    value_expr = "value_numeric" if "value_numeric" in schema.columns else "NULL AS value_numeric"
    optional = _optional_selects(schema.columns)
    sql = f"""
        SELECT metric_key, observation_date, {value_expr}{optional}
        FROM {schema.table_name}
        WHERE metric_key = ?
        ORDER BY observation_date ASC
    """
    return [dict(row) for row in connection.execute(sql, (metric_key,)).fetchall()]


def _read_source_series_rows(
    connection: sqlite3.Connection,
    schema: TableSchema,
    series_id: str,
) -> list[dict[str, Any]]:
    value_expr = "value_numeric" if "value_numeric" in schema.columns else "NULL AS value_numeric"
    optional = _optional_selects(schema.columns)
    sql = f"""
        SELECT metric_key, observation_date, {value_expr}{optional}
        FROM {schema.table_name}
        WHERE source_series = ?
        ORDER BY observation_date ASC
    """
    return [dict(row) for row in connection.execute(sql, (series_id,)).fetchall()]


def _optional_selects(columns: set[str]) -> str:
    parts = []
    for column in ("source_series", "source_badge", "status"):
        if column in columns:
            parts.append(column)
        else:
            parts.append(f"NULL AS {column}")
    return ", " + ", ".join(parts)


def _find_compatible_table(connection: sqlite3.Connection) -> TableSchema | None:
    tables = [
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    ]
    ordered = list(DEFAULT_TABLE_CANDIDATES) + sorted(
        table for table in tables if table not in DEFAULT_TABLE_CANDIDATES
    )
    for table in ordered:
        if table not in tables:
            continue
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if {"metric_key", "observation_date"}.issubset(columns):
            return TableSchema(table, columns)
    return None


def _probe_fred_series_range(series_id: str, *, timeout_seconds: int) -> dict[str, Any]:
    api_key = os.getenv("FRED_API_KEY")
    if api_key:
        result = _probe_fred_api(series_id, api_key, timeout_seconds=timeout_seconds)
        if result.get("status") == "ok":
            return result
    return _probe_fred_public_csv(series_id, timeout_seconds=timeout_seconds)


def _probe_fred_api(series_id: str, api_key: str, *, timeout_seconds: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "asc",
            "observation_start": "1776-07-04",
            "limit": 100000,
        }
    )
    url = f"{FRED_API_URL}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        observations = payload.get("observations")
        if not isinstance(observations, list):
            return _provider_error(series_id, "fred_api", "fred_api_missing_observations")
        points = [
            (item.get("date"), _to_float_or_none(item.get("value")))
            for item in observations
        ]
        return _provider_summary(series_id, "fred_api", points)
    except Exception as exc:
        return _provider_error(series_id, "fred_api", f"{type(exc).__name__}")


def _probe_fred_public_csv(series_id: str, *, timeout_seconds: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({"id": series_id})
    url = f"{FRED_CSV_URL}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        points = [(row.get("observation_date") or row.get("DATE"), _to_float_or_none(row.get(series_id))) for row in reader]
        return _provider_summary(series_id, "fred_public_csv", points)
    except Exception as exc:
        return _provider_error(series_id, "fred_public_csv", f"{type(exc).__name__}")


def _provider_summary(
    series_id: str,
    query_method: str,
    points: list[tuple[Any, float | None]],
) -> dict[str, Any]:
    numeric = [
        (parsed, value)
        for raw_date, value in points
        for parsed in [_parse_date(raw_date)]
        if parsed is not None and value is not None
    ]
    numeric.sort(key=lambda item: item[0])
    if not numeric:
        return _provider_error(series_id, query_method, "no_numeric_observations")
    dates = [item[0] for item in numeric]
    latest_date, latest_value = numeric[-1]
    span_days = (dates[-1] - dates[0]).days
    return {
        "series_id": series_id,
        "provider": "FRED",
        "status": "ok",
        "provider_start_now": dates[0].isoformat(),
        "provider_end_now": dates[-1].isoformat(),
        "provider_non_null_count": len(numeric),
        "provider_coverage_years": round(span_days / 365.25, 3) if span_days else 0.0,
        "latest_value": latest_value,
        "latest_date": latest_date.isoformat(),
        "frequency_detected": _frequency_guess(dates),
        "query_method": query_method,
        "notes_detected_if_available": _provider_note(span_days),
    }


def _provider_error(series_id: str, query_method: str, error_type: str) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "provider": "FRED",
        "status": "error",
        "provider_start_now": None,
        "provider_end_now": None,
        "provider_non_null_count": 0,
        "latest_value": None,
        "latest_date": None,
        "frequency_detected": None,
        "query_method": query_method,
        "notes_detected_if_available": error_type,
    }


def _d13_eligibility(local: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    del provider
    metrics: dict[str, Any] = {}
    for metric_key, summary in local.get("metrics", {}).items():
        span_days = int(summary.get("local_coverage_days") or 0)
        count = int(summary.get("local_non_null_count") or 0)
        can_3y = span_days >= THREE_YEAR_DAYS and count >= MINIMUM_OBSERVATION_COUNT
        can_5y = span_days >= FIVE_YEAR_DAYS and count >= MINIMUM_OBSERVATION_COUNT
        can_10y = span_days >= TEN_YEAR_DAYS and count >= MINIMUM_OBSERVATION_COUNT
        can_long = span_days >= LONG_HISTORY_DAYS and count >= MINIMUM_OBSERVATION_COUNT
        if can_5y:
            status = "sufficient"
        elif can_3y:
            status = "limited_history"
        elif count:
            status = "insufficient_history"
        else:
            status = "no_local_history"
        metrics[metric_key] = {
            "can_compute_3y_rolling": can_3y,
            "can_compute_5y_rolling": can_5y,
            "can_compute_10y_reference": can_10y,
            "can_compute_long_history_reference": can_long,
            "current_recommended_d13_status": status,
            "recommended_metadata_flags": _recommended_metadata_flags(summary, can_3y, can_5y, can_long),
        }
    return {"metrics": metrics}


def _recommended_metadata_flags(
    summary: dict[str, Any],
    can_3y: bool,
    can_5y: bool,
    can_long: bool,
) -> list[str]:
    flags = []
    if summary.get("local_non_null_count"):
        flags.append("local_reference_available")
    if not can_5y:
        flags.append("provider_rebuild_limited")
    if not can_3y:
        flags.append("below_exact_3y_gate")
    if can_3y and not can_5y:
        flags.append("limited_3y_history")
    if can_long:
        flags.append("long_history_reference_available")
    else:
        flags.append("long_history_reference_unavailable")
    return flags


def _d19_impact(local: dict[str, Any]) -> dict[str, Any]:
    metrics = local.get("metrics", {})
    event_results = []
    for event_id, start, end in EVENT_WINDOWS:
        metric_coverage = {
            key: _event_has_metric_coverage(summary, start, end)
            for key, summary in metrics.items()
        }
        event_results.append(
            {
                "event_id": event_id,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "credit_coverage": all(metric_coverage.values()) if metric_coverage else False,
                "metric_coverage": metric_coverage,
            }
        )
    upgraded = [item["event_id"] for item in event_results if item["credit_coverage"]]
    insufficient = [item["event_id"] for item in event_results if not item["credit_coverage"]]
    return {
        "event_windows": event_results,
        "event_windows_improved_by_local_credit_history": upgraded,
        "event_windows_still_insufficient_for_credit": insufficient,
        "recommended_use": "D19 historical reference only; do not convert local-only history into production trigger.",
        "project_event_registry_ids": [event.event_id for event in historical_validation.EVENT_WINDOWS],
    }


def _event_has_metric_coverage(summary: dict[str, Any], start: date, end: date) -> bool:
    local_start = _parse_date(summary.get("local_start"))
    local_end = _parse_date(summary.get("local_end"))
    if local_start is None or local_end is None:
        return False
    return local_start <= start and local_end >= end


def _license_boundary(provider: dict[str, Any]) -> dict[str, Any]:
    full_rebuild = all(
        (item.get("status") == "ok" and int(item.get("provider_coverage_years") or 0) >= 20)
        for key, item in provider.items()
        if key in {"BAMLH0A0HYM2", "BAMLC0A0CM"}
    ) if provider else None
    return {
        "current_fred_can_rebuild_full_history": full_rebuild,
        "local_ignored_db_use": "allowed_for_local_audit_and_reference_only",
        "raw_data_commit_or_redistribution": "not_allowed",
        "coverage_summary_commit": "allowed",
        "raw_provider_payload_commit": "not_allowed",
    }


def _coverage_status(span_days: int, count: int) -> str:
    if count <= 0:
        return "no_local_history"
    if span_days >= FIVE_YEAR_DAYS:
        return "sufficient"
    if span_days >= THREE_YEAR_DAYS:
        return "limited_history"
    return "insufficient_history"


def _empty_local_metric(metric_key: str, reason: str) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "series_id": TARGET_METRICS[metric_key]["series_id"],
        "matched_by": None,
        "local_start": None,
        "local_end": None,
        "local_non_null_count": 0,
        "local_row_count": 0,
        "local_null_count": 0,
        "local_distinct_date_count": 0,
        "local_coverage_days": 0,
        "local_coverage_years": 0.0,
        "local_frequency_guess": None,
        "source_series_detected": [],
        "source_badges_detected": [],
        "statuses_detected": [],
        "gaps": {"gap_count_gt_10_days": 0, "max_gap_days": 0, "sample_gaps": []},
        "duplicate_observations": {"duplicate_date_count": 0, "max_rows_on_same_date": 0},
        "abnormal_null_count": 0,
        "coverage_status": reason,
    }


def _gap_summary(dates: list[date]) -> dict[str, Any]:
    gaps = []
    for left, right in zip(dates, dates[1:]):
        days = (right - left).days
        if days > 10:
            gaps.append(
                {
                    "from": left.isoformat(),
                    "to": right.isoformat(),
                    "gap_days": days,
                }
            )
    return {
        "gap_count_gt_10_days": len(gaps),
        "max_gap_days": max((gap["gap_days"] for gap in gaps), default=0),
        "sample_gaps": gaps[:5],
    }


def _duplicate_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        observation_date = row.get("observation_date")
        if observation_date:
            counts[str(observation_date)] = counts.get(str(observation_date), 0) + 1
    duplicate_counts = [count for count in counts.values() if count > 1]
    return {
        "duplicate_date_count": len(duplicate_counts),
        "max_rows_on_same_date": max(duplicate_counts, default=0),
    }


def _frequency_guess(dates: list[date]) -> str | None:
    if len(dates) < 2:
        return None
    gaps = [(right - left).days for left, right in zip(dates, dates[1:]) if right > left]
    if not gaps:
        return None
    median_gap = median(gaps)
    span_years = max((dates[-1] - dates[0]).days / 365.25, 1 / 365.25)
    observations_per_year = len(dates) / span_years
    if median_gap <= 3 and observations_per_year >= 180:
        return "daily_market_or_business_day"
    if 5 <= median_gap <= 9:
        return "weekly"
    if 25 <= median_gap <= 35:
        return "monthly"
    return f"irregular_median_gap_{median_gap:g}_days"


def _provider_note(span_days: int) -> str:
    if span_days >= LONG_HISTORY_DAYS:
        return "Current provider still returns long history in this environment. Do not commit or redistribute raw data."
    if span_days >= THREE_YEAR_DAYS - 31 and span_days < FIVE_YEAR_DAYS:
        return "Current FRED provider availability appears limited to approximately 3 years. Do not treat this as reproducible full-history source."
    return "Current provider range is shorter than the project long-history reference requirement."


def _distinct_values(rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(row.get(key)) for row in rows if row.get(key) not in (None, "")})


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _to_float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == ".":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return "<external_market_history_db>"


def _format_text(result: dict[str, Any]) -> str:
    lines = [
        "D13 Credit OAS History Availability Audit",
        f"mode: {result['mode']}",
        "",
        "Local market_history coverage:",
    ]
    for metric_key, item in result["local_market_history"]["metrics"].items():
        lines.append(
            "- "
            f"{metric_key}: {item['local_start']} to {item['local_end']}, "
            f"count={item['local_non_null_count']}, "
            f"years={item['local_coverage_years']}, "
            f"frequency={item['local_frequency_guess']}, "
            f"status={item['coverage_status']}"
        )
    if result["fred_provider_availability"]:
        lines.extend(["", "Current FRED provider availability:"])
        for series_id, item in result["fred_provider_availability"].items():
            lines.append(
                "- "
                f"{series_id}: {item['provider_start_now']} to {item['provider_end_now']}, "
                f"count={item['provider_non_null_count']}, "
                f"latest={item['latest_date']}, "
                f"method={item['query_method']}, "
                f"note={item['notes_detected_if_available']}"
            )
    lines.extend(["", "D13 eligibility:"])
    for metric_key, item in result["d13_eligibility"]["metrics"].items():
        lines.append(
            "- "
            f"{metric_key}: 3Y={item['can_compute_3y_rolling']}, "
            f"5Y={item['can_compute_5y_rolling']}, "
            f"10Y={item['can_compute_10y_reference']}, "
            f"long={item['can_compute_long_history_reference']}, "
            f"status={item['current_recommended_d13_status']}"
        )
    lines.extend(
        [
            "",
            "D19 impact:",
            "- improved_credit_windows="
            + ",".join(result["d19_historical_validation_impact"]["event_windows_improved_by_local_credit_history"]),
            "- insufficient_credit_windows="
            + ",".join(result["d19_historical_validation_impact"]["event_windows_still_insufficient_for_credit"]),
            "",
            "Boundary:",
            "- raw data commit or redistribution: not_allowed",
            "- coverage summary commit: allowed",
        ]
    )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit local and current-provider coverage for HY/IG credit OAS history."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local-only", action="store_true", help="Read local SQLite only; no network.")
    mode.add_argument("--probe-fred-range", action="store_true", help="Probe current FRED range; no DB writes.")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON summary.")
    parser.add_argument("--market-history-db", type=Path, default=None, help="Optional market_history SQLite path.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="Provider probe timeout.")
    args = parser.parse_args(argv)
    if not args.local_only and not args.probe_fred_range:
        args.local_only = True
    return args


if __name__ == "__main__":
    raise SystemExit(main())
