from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app_backend.schemas.responses import DashboardEvidenceRow  # noqa: E402
from data_quality import liquidity_funding_stress as d14_liquidity_funding  # noqa: E402


STATUS_KEYS = (
    "ok",
    "watch",
    "pressure",
    "missing",
    "research_needed",
    "insufficient_history",
    "insufficient_evidence",
    "stale",
    "unknown",
)
BAD_FRESHNESS = {"unknown", "missing", "stale"}
BAD_AI_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "insufficient_evidence",
    "stale",
}
BAD_AI_SOURCE_BADGES = {"missing", "research_needed", "search-derived"}
DEFAULT_YFINANCE_HISTORY_CONFIG = PROJECT_ROOT / "configs" / "yfinance_history.yaml"
PROXY_BREADTH_METRIC_KEYS = {
    "spy_proxy_30d_return",
    "spy_proxy_60d_return",
    "rsp_proxy_30d_return",
    "rsp_proxy_60d_return",
    "qqq_proxy_30d_return",
    "qqq_proxy_60d_return",
    "spy_vs_rsp_30d",
    "spy_vs_rsp_60d",
    "qqq_vs_spy_30d",
    "qqq_vs_spy_60d",
    "hyg_vs_lqd_30d",
    "hyg_vs_lqd_60d",
}
CONCENTRATION_PROXY_METRIC_KEYS = {
    "spy_vs_rsp_30d",
    "spy_vs_rsp_60d",
    "qqq_vs_spy_30d",
    "qqq_vs_spy_60d",
}
CREDIT_PROXY_METRIC_KEYS = {
    "hyg_vs_lqd_30d",
    "hyg_vs_lqd_60d",
}
MARKET_STRESS_DERIVED_METRIC_KEYS = {
    "sp500_drawdown_3m",
    "sp500_drawdown_6m",
    "nasdaq100_drawdown_3m",
    "nasdaq100_drawdown_6m",
    "dgs10_dgs2_curve_slope",
    "dgs30_dgs10_curve_slope",
    "tlt_proxy_30d_return",
    "gld_proxy_30d_return",
    "shy_proxy_30d_return",
    "tlt_vs_shy_30d",
}
DRAWDOWN_METRIC_KEYS = {
    "sp500_drawdown_3m",
    "sp500_drawdown_6m",
    "nasdaq100_drawdown_3m",
    "nasdaq100_drawdown_6m",
}
CURVE_SLOPE_METRIC_KEYS = {
    "dgs10_dgs2_curve_slope",
    "dgs30_dgs10_curve_slope",
}
CROSS_ASSET_PROXY_METRIC_KEYS = {
    "tlt_proxy_30d_return",
    "gld_proxy_30d_return",
    "shy_proxy_30d_return",
    "tlt_vs_shy_30d",
}
FINANCIAL_STRESS_COMPOSITE_METRIC_KEYS = {
    "financial_stress_score",
    "financial_stress_status",
    "financial_stress_dominant_pressure_source",
    "financial_stress_component_contributions",
    "financial_stress_missing_inputs",
    "financial_stress_interpretation_boundary",
    "financial_stress_percentile_context",
    "financial_stress_funding_liquidity_context",
}
PULLBACK_SYSTEMIC_CHECKLIST_METRIC_KEYS = {
    "pullback_classification",
    "pullback_checklist_items",
    "pullback_missing_critical_inputs",
    "pullback_supporting_evidence",
    "pullback_interpretation_boundary",
    "pullback_percentile_context",
    "pullback_liquidity_funding_context",
}
HISTORICAL_RISK_PERCENTILE_METRIC_KEYS = {
    "high_yield_spread_percentile",
    "high_yield_spread_zscore",
    "high_yield_spread_robust_zscore",
    "investment_grade_spread_percentile",
    "investment_grade_spread_zscore",
    "investment_grade_spread_robust_zscore",
    "vix_percentile",
    "vix_zscore",
    "vix_robust_zscore",
    "dgs30_percentile",
    "dgs30_zscore",
    "dgs30_robust_zscore",
    "dfii10_percentile",
    "dfii10_zscore",
    "dfii10_robust_zscore",
    "sp500_drawdown_3m_percentile",
    "sp500_drawdown_3m_robust_zscore",
    "nasdaq100_drawdown_3m_percentile",
    "nasdaq100_drawdown_3m_robust_zscore",
    "initial_claims_4w_avg_percentile",
    "initial_claims_4w_avg_robust_zscore",
    "continuing_claims_4w_avg_percentile",
    "continuing_claims_4w_avg_robust_zscore",
}
LIQUIDITY_FUNDING_RAW_METRIC_KEYS = set(d14_liquidity_funding.RAW_METRIC_KEYS)
LIQUIDITY_FUNDING_DERIVED_METRIC_KEYS = set(d14_liquidity_funding.DERIVED_METRIC_KEYS)
LIQUIDITY_FUNDING_METRIC_KEYS = set(d14_liquidity_funding.ALL_METRIC_KEYS)
CORE_RISK_RAW_METRIC_KEYS = {
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
CORE_RISK_DERIVED_METRIC_KEYS = {
    "sp500_drawdown_3m",
    "nasdaq100_drawdown_3m",
    "initial_claims_4w_avg",
    "continuing_claims_4w_avg",
}



def _metric_count_map(rows: list[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        result[str(row["metric_key"])] = result.get(str(row["metric_key"]), 0) + int(row["count"])
    return dict(sorted(result.items()))

def _badge_count_map(rows: list[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        result[str(row["source_badge"])] = result.get(str(row["source_badge"]), 0) + int(row["count"])
    return dict(sorted(result.items()))

def _row_status(row: DashboardEvidenceRow | None) -> str:
    return row.status if row is not None else "missing"

def _compact_dgs_fallback_observations(
    rows: list[DashboardEvidenceRow],
) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.metric_key not in {"dgs2", "dgs10", "dgs30"}:
            continue
        source_series = row.source_series
        if source_series is None and row.source_badge == "official":
            source_series = row.metric_key.upper()
        observations[row.metric_key] = {
            "value": row.value,
            "source": row.source,
            "source_badge": row.source_badge,
            "source_series": source_series,
            "observation_date": row.observation_date,
            "generated_at": row.generated_at,
            "freshness_status": row.freshness_status,
            "ai_context_allowed": row.ai_context_allowed,
        }
    return observations

def _row_payload(row: DashboardEvidenceRow) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        return row.model_dump()
    return row.dict()

def _anomaly(
    row: DashboardEvidenceRow | None,
    anomaly_type: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "type": anomaly_type,
        "reason": reason or (row.blocked_reason if row is not None else None),
        "module": row.module if row is not None else None,
        "metric_key": row.metric_key if row is not None else None,
        "row_id": row.row_id if row is not None else None,
        "detail": _anomaly_detail(row),
    }

def _anomaly_detail(row: DashboardEvidenceRow | None) -> str:
    if row is None:
        return "referenced row is absent"
    return (
        f"status={row.status}; source_badge={row.source_badge}; "
        f"freshness_status={row.freshness_status}; ai_context_allowed={row.ai_context_allowed}"
    )

def _has_value(row: DashboardEvidenceRow) -> bool:
    return row.value is not None

def _yoy_metric_suspiciously_large(row: DashboardEvidenceRow) -> bool:
    if "yoy" not in row.metric_key.lower() or not _has_value(row):
        return False
    try:
        value = float(row.value)
    except (TypeError, ValueError):
        return False
    return abs(value) > 50.0

def _is_missing_source_badge(value: str | None) -> bool:
    return value in {None, "", "missing"}

def _has_complete_metadata(row: DashboardEvidenceRow) -> bool:
    if _is_missing_source_badge(row.source_badge):
        return False
    if row.freshness_status in {"unknown", "missing", "stale", "insufficient_history"}:
        return False
    return bool(row.observation_date or row.generated_at)

def _provenance_missing(row: DashboardEvidenceRow) -> bool:
    return (
        _is_missing_source_badge(row.source_badge)
        or row.freshness_status in {"unknown", "missing"}
        or (not row.observation_date and not row.generated_at)
    )

def _source_missing(row: DashboardEvidenceRow | None) -> bool:
    if row is None:
        return True
    if row.value is None:
        return True
    if row.status in BAD_AI_STATUSES:
        return True
    if row.freshness_status in {"missing", "insufficient_history", "stale"}:
        return True
    return False

def _row_has_ok_value(row: DashboardEvidenceRow | None) -> bool:
    return bool(row is not None and row.status == "ok" and row.value is not None)

def _has_clear_history_hint(row: DashboardEvidenceRow | None) -> bool:
    if row is None:
        return False
    hint = (row.interpretation_hint or "").lower()
    reason = (row.missing_reason or "").lower()
    return "30 day" in hint or "30d" in hint or "history" in hint or "history" in reason
