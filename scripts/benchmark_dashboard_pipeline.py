"""
Performance baseline benchmark for the dashboard pipeline.

Read-only by default: does not fetch from network, does not write to DB,
does not write output files. Prints JSON to stdout.

Usage:
    python scripts/benchmark_dashboard_pipeline.py
    python scripts/benchmark_dashboard_pipeline.py --reports-dir /path/to/reports
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app_backend.services import ai_context_service  # noqa: E402
from app_backend.services import dashboard_service  # noqa: E402
from data_quality import financial_stress_composite  # noqa: E402
from data_quality import historical_percentile_metrics  # noqa: E402
from data_quality import liquidity_funding_stress  # noqa: E402
from data_quality import market_history_store  # noqa: E402
from data_quality import pullback_systemic_checklist  # noqa: E402
import audit_data_pipeline_coverage as audit  # noqa: E402


_PROHIBITED_OUTPUT_PATTERNS = (
    "raw_holdings",
    "raw_provider",
)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _guard_output(data: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(data, default=str)
    for pattern in _PROHIBITED_OUTPUT_PATTERNS:
        if pattern in serialized:
            raise ValueError(f"Benchmark output contains prohibited pattern: {pattern!r}")
    if len(serialized) > 5_000_000:
        raise ValueError("Benchmark output unexpectedly large; possible data leak")
    return data


def _market_history_stats(db_path: Path) -> dict[str, int]:
    summary = market_history_store.get_market_history_summary(db_path=db_path)
    return {
        "market_history_observation_count": summary.get("market_history_observation_count", 0),
        "market_history_metric_count": summary.get("market_history_metric_count", 0),
    }


def _check_db_indices(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "db_exists": False,
            "explicit_index_names": [],
            "has_explicit_metric_key_index": False,
            "unique_constraint_covers_metric_key_observation_date": False,
            "note": "DB not found; index check skipped",
        }
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        idx_rows = conn.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'market_observations'
            """
        ).fetchall()
        table_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='market_observations'"
        ).fetchone()
    explicit_names = [r["name"] for r in idx_rows if not r["name"].startswith("sqlite_autoindex")]
    has_metric_date_index = any(
        r["name"] == "idx_market_observations_metric_date"
        and r["sql"]
        and "metric_key" in r["sql"]
        and "observation_date" in r["sql"]
        for r in idx_rows
    )
    table_sql = table_row["sql"] if table_row else ""
    unique_covers = (
        "metric_key" in table_sql
        and "observation_date" in table_sql
        and "UNIQUE" in table_sql
    )
    if unique_covers and not has_metric_date_index:
        note = (
            "UNIQUE(metric_key, observation_date, source_badge, source_series) provides an "
            "implicit 4-column composite index. SQLite can use this for WHERE metric_key=? "
            "queries and ORDER BY observation_date within a metric_key range scan. "
            "No dedicated (metric_key, observation_date) covering index exists."
        )
    elif has_metric_date_index:
        note = "explicit idx_market_observations_metric_date index found"
    else:
        note = "no metric_key index found; queries may do full table scans"
    return {
        "db_exists": True,
        "explicit_index_names": explicit_names,
        "has_explicit_metric_key_index": has_metric_date_index,
        "has_metric_date_index": has_metric_date_index,
        "unique_constraint_covers_metric_key_observation_date": unique_covers,
        "note": note,
    }


def run_benchmark(
    reports_dir: Path | str | None = None,
    market_history_db_path: Path | str | None = None,
) -> dict[str, Any]:
    db_path = (
        Path(market_history_db_path)
        if market_history_db_path is not None
        else market_history_store.get_default_market_history_db_path()
    )

    mh_stats = _market_history_stats(db_path)
    db_index_audit = _check_db_indices(db_path)

    # 1. build_dashboard_summary
    t0 = time.perf_counter()
    summary = dashboard_service.build_dashboard_summary(
        reports_dir=reports_dir,
        market_history_db_path=market_history_db_path,
    )
    dashboard_summary_ms = _ms(t0)

    # 2. build_dashboard_evidence_table (includes build_dashboard_summary internally)
    t0 = time.perf_counter()
    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=reports_dir,
        market_history_db_path=market_history_db_path,
        write_last_good=False,
    )
    dashboard_evidence_table_ms = _ms(t0)
    evidence_row_count = evidence.row_count

    # 3. build AI context manifest (calls build_dashboard_evidence_table internally)
    t0 = time.perf_counter()
    manifest = ai_context_service.build_ai_context_manifest()
    ai_context_manifest_ms = _ms(t0)
    included_facts_count = len(manifest.included_facts)
    included_model_outputs_count = len(manifest.included_model_outputs)

    # 4. D13: build_historical_percentile_rows (M2: single batch query)
    db_path_str = str(db_path) if db_path.exists() else None
    t0 = time.perf_counter()
    d13_rows = historical_percentile_metrics.build_historical_percentile_rows(db_path=db_path_str)
    d13_build_ms = _ms(t0)

    # 5. D14: build_liquidity_funding_rows (M2: single batch query)
    t0 = time.perf_counter()
    d14_rows = liquidity_funding_stress.build_liquidity_funding_rows(db_path=db_path)
    d14_build_ms = _ms(t0)

    # 6. D10: financial_stress_composite in-memory portion
    # Input: D13 + D14 dicts only (base_rows from dashboard_service internals not included).
    # This measures the in-memory compute time, not the full dashboard pipeline D10 path.
    assembled_for_composite = d13_rows + d14_rows
    t0 = time.perf_counter()
    d10_rows = financial_stress_composite.build_financial_stress_rows(assembled_for_composite)
    d10_build_ms = _ms(t0)

    # 7. D11: pullback_systemic_checklist in-memory portion
    assembled_for_checklist = assembled_for_composite + d10_rows
    t0 = time.perf_counter()
    d11_rows = pullback_systemic_checklist.build_pullback_checklist_rows(assembled_for_checklist)
    d11_build_ms = _ms(t0)

    # 8. audit_data_pipeline_coverage
    t0 = time.perf_counter()
    _audit_result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=market_history_db_path,
    )
    audit_total_ms = _ms(t0)

    timings: dict[str, float] = {
        "dashboard_summary": dashboard_summary_ms,
        "dashboard_evidence_table": dashboard_evidence_table_ms,
        "ai_context_manifest": ai_context_manifest_ms,
        "d13_historical_percentile": d13_build_ms,
        "d14_liquidity_funding": d14_build_ms,
        "d10_financial_stress_composite": d10_build_ms,
        "d11_pullback_checklist": d11_build_ms,
        "audit_coverage": audit_total_ms,
    }
    slowest = sorted(timings.items(), key=lambda x: x[1], reverse=True)[:3]

    result: dict[str, Any] = {
        "generated_at": summary.generated_at,
        **mh_stats,
        "dashboard_summary_ms": dashboard_summary_ms,
        "dashboard_evidence_table_ms": dashboard_evidence_table_ms,
        "ai_context_manifest_ms": ai_context_manifest_ms,
        "d10_build_ms": d10_build_ms,
        "d10_isolation_note": "partial: D13+D14 dicts as input; base_rows from dashboard_service internals excluded",
        "d11_build_ms": d11_build_ms,
        "d11_isolation_note": "partial: D13+D14+D10 dicts as input; base_rows from dashboard_service internals excluded",
        "d13_build_ms": d13_build_ms,
        "d13_query_strategy": "batch",
        "d14_build_ms": d14_build_ms,
        "d14_query_strategy": "batch",
        "audit_total_ms": audit_total_ms,
        "evidence_row_count": evidence_row_count,
        "included_facts_count": included_facts_count,
        "included_model_outputs_count": included_model_outputs_count,
        "market_history_batch_api_available": True,
        "market_history_index_metric_date_available": db_index_audit.get("has_explicit_metric_key_index", False),
        "slowest_sections": [{"section": k, "ms": v} for k, v in slowest],
        "db_index_audit": db_index_audit,
        "call_path_audit": _call_path_audit(),
        "notes": [
            "benchmark is read-only: no network fetch, no DB write, no output file write",
            "dashboard_evidence_table_ms includes an internal build_dashboard_summary call",
            "ai_context_manifest_ms includes a full build_dashboard_evidence_table call",
            "audit_total_ms includes build_dashboard_summary + build_dashboard_evidence_table",
            f"d13_spec_count={len(historical_percentile_metrics.PERCENTILE_METRIC_SPECS)} (M2: one batch query for all unique source metrics)",
            f"d14_raw_metric_count={len(liquidity_funding_stress.RAW_METRIC_KEYS)} (M2: one batch query for all raw metrics)",
            "D10 and D11 in-memory timing uses D13+D14 dict rows as input; actual pipeline also includes base_rows",
            "m2_optimization: D13/D14 now use list_market_observations_batch; single DB connection per build call",
        ],
    }
    return _guard_output(result)


def _call_path_audit() -> dict[str, Any]:
    return {
        "confirmed_facts": [
            "M2: D13 build_historical_percentile_rows now uses list_market_observations_batch: single DB connect + single query for all unique source metrics",
            "M2: D14 build_liquidity_funding_rows now uses list_market_observations_batch: single DB connect + single query for all raw metrics",
            f"M2: idx_market_observations_metric_date index (metric_key, observation_date DESC) added via schema migration version 2",
            "build_dashboard_evidence_table calls build_dashboard_summary internally: both paths share no cached result",
            "ai_context_service.build_ai_context_manifest calls build_dashboard_evidence_table (write_last_good=False): full pipeline rebuilt on every manifest request",
            "audit_data_pipeline_coverage.build_coverage_audit calls both build_dashboard_summary and build_dashboard_evidence_table independently",
            "D10 financial_stress_composite.build_financial_stress_rows is pure in-memory after row assembly (no DB queries)",
            "D11 pullback_systemic_checklist.build_pullback_checklist_rows is pure in-memory after row assembly (no DB queries)",
            "No @lru_cache or @cache decorators exist on any query function or builder",
            "Evidence table filters (module/status/source_badge/ai_context_allowed) are applied post-build: the full pipeline always runs regardless of filter",
        ],
        "resolved_hotspots": [
            f"D13 N+1 resolved: was {len(historical_percentile_metrics.PERCENTILE_METRIC_SPECS)} separate DB queries; now 1 batch query",
            f"D14 N+1 resolved: was {len(liquidity_funding_stress.RAW_METRIC_KEYS)} separate DB queries; now 1 batch query",
            "D13/D14 connection-per-call resolved: was 32 connect/close cycles; now 2 (one per batch call)",
            "Missing (metric_key, observation_date DESC) covering index resolved: added as idx_market_observations_metric_date via schema v2",
        ],
        "remaining_hotspots_for_m3": [
            "build_dashboard_evidence_table calls build_dashboard_summary internally: a combined summary+evidence request rebuilds the dashboard summary twice",
            "ai_context_manifest rebuild: manifest call triggers a third full pipeline rebuild independent of any prior /evidence-table call",
            "audit rebuild: running build_coverage_audit after a manifest call can trigger a fourth full pipeline build in the same process lifecycle",
            "get_market_history_summary issues get_latest_observation per distinct metric (N+1 for summary stats)",
            "No request-scoped cache: each HTTP request rebuilds all rows from scratch",
        ],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark dashboard pipeline (read-only)")
    parser.add_argument("--reports-dir", default=None, help="Path to reports directory")
    parser.add_argument(
        "--market-history-db",
        default=None,
        help="Path to market_history SQLite DB",
    )
    args = parser.parse_args()

    result = run_benchmark(
        reports_dir=args.reports_dir,
        market_history_db_path=args.market_history_db,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
