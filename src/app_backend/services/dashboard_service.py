from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import (
    DashboardEvidenceRow,
    DashboardEvidenceTableResponse,
    DashboardMetric,
    DashboardModule,
    DashboardSummaryResponse,
)
from app_backend.services import provider_service
from data_quality import historical_derived_metrics
from data_quality import last_good_cache
from data_quality import market_history_store
from data_quality import official_macro_pack


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
DEFAULT_REPORTS_DIR = PROJECT_REPORTS_DIR
DEFAULT_MARKET_HISTORY_DB_PATH = market_history_store.get_default_market_history_db_path()
MAX_ERROR_SUMMARY_LENGTH = 200
DASHBOARD_MODULE_KEYS = (
    "credit_stress",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy_pressure",
    "equity_trend",
    "breadth_concentration_proxy",
    "market_stress_derived",
    "portfolio_deviation",
)
REPORT_FILES = {
    "market_snapshot": "market_snapshot.json",
    "market_temperature": "market_temperature.json",
    "portfolio_snapshot": "portfolio_snapshot.json",
    "provider_health": "provider_health_check.json",
}
OPTIONAL_METADATA_REPORT_FILES = {
    "llm_context_pack": "llm_context_pack.json",
}
ALLOWED_METRIC_STATUSES = {
    "ok",
    "watch",
    "pressure",
    "stress",
    "missing",
    "stale",
    "unknown",
    "research_needed",
    "insufficient_history",
    "not_available",
}
ALLOWED_SOURCE_BADGES = {
    "official",
    "official_fallback",
    "unofficial_fallback",
    "proxy",
    "search-derived",
    "missing",
    "research_needed",
    "local",
    "derived",
}
AI_BLOCKED_METRIC_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "stale",
}
AI_BLOCKED_FRESHNESS_STATUSES = {
    "unknown",
    "missing",
    "stale",
    "insufficient_history",
}
AI_BLOCKED_SOURCE_BADGES = {
    "missing",
    "research_needed",
    "search-derived",
}
DERIVED_METRIC_KEYS = {
    "dgs10_5d_avg",
    "dgs30_distance_to_5pct",
    "dgs30_breakout_confirmed",
    "sp500_30d_return",
    "sp500_60d_return",
    "nasdaq100_30d_return",
    "nasdaq100_60d_return",
    "nasdaq_vs_sp500_30d",
    "wti_30d_change",
    "brent_30d_change",
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
    "unemployment_rate_3m_avg",
    "unemployment_rate_12m_low_gap",
    "initial_claims_4w_avg",
    "continuing_claims_4w_avg",
    "sahm_rule_proxy_status",
    "labor_deterioration_status",
}
EQUITY_HISTORICAL_DERIVED_METRIC_KEYS = {
    "sp500_30d_return",
    "sp500_60d_return",
    "nasdaq100_30d_return",
    "nasdaq100_60d_return",
    "nasdaq_vs_sp500_30d",
}
OIL_HISTORICAL_DERIVED_METRIC_KEYS = {
    "wti_30d_change",
    "brent_30d_change",
}
PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS = {
    "ppi_final_demand_yoy",
}
PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS = {
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
MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS = {
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
LABOR_HISTORICAL_DERIVED_METRIC_KEYS = {
    "unemployment_rate_3m_avg",
    "unemployment_rate_12m_low_gap",
    "initial_claims_4w_avg",
    "continuing_claims_4w_avg",
    "sahm_rule_proxy_status",
    "labor_deterioration_status",
}
EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX = (
    " Derived from local market history; underlying source includes yfinance "
    "unofficial_fallback/proxy observations in the market history store; not an "
    "official market breadth or valuation measure."
)
OIL_HISTORICAL_DERIVED_HINT_SUFFIX = (
    " Derived from official FRED/EIA daily oil history in local market history; "
    "this remains a derived energy-pressure input, not a real-time oil quote, "
    "inflation forecast, or commodity trading signal."
)
METRIC_ALIASES = {
    "wti_30d_change": ("wti_oil_30d_change",),
    "brent_30d_change": ("brent_oil_30d_change",),
}
INFLATION_YOY_METRIC_KEYS = {
    "core_cpi_yoy",
    "core_pce_yoy",
    "ppiaco_yoy",
    "ppi_final_demand_yoy",
}
INDEX_LEVEL_YOY_MISSING_REASON = (
    "Only index level is available; YoY requires historical comparison."
)
DGS30_BREAKOUT_MISSING_REASON = "Requires explicit confirmation rule and sufficient DGS30 history."
LABOR_METRIC_SPECS = [
    ("unemployment_rate", "Unemployment rate", "percent", "percent", "missing"),
    ("initial_jobless_claims", "Initial jobless claims", "claims", "number", "missing"),
    ("nonfarm_payrolls", "Nonfarm payrolls", "thousand_persons", "number", "missing"),
    ("continuing_claims", "Continuing claims", "claims", "number", "missing"),
    (
        "unemployment_rate_3m_avg",
        "Unemployment rate 3M average",
        "percent",
        "percent",
        "insufficient_history",
    ),
    (
        "unemployment_rate_12m_low_gap",
        "Unemployment 12M low gap",
        "pp",
        "pp",
        "insufficient_history",
    ),
    ("initial_claims_4w_avg", "Initial claims 4W average", "claims", "number", "insufficient_history"),
    ("continuing_claims_4w_avg", "Continuing claims 4W average", "claims", "number", "insufficient_history"),
    ("sahm_rule_proxy_status", "Sahm rule proxy status", None, "text", "insufficient_history"),
    ("labor_deterioration_status", "Labor deterioration status", None, "text", "insufficient_history"),
]
SOURCE_BADGE_ALIASES = {
    "official_api": "official",
    "official_or_public_data_api": "official",
    "public_data_api": "official",
    "third_party_api": "proxy",
    "manual": "local",
    "cached_report": "derived",
}
CORE_METRIC_KEYS = {
    "credit_stress": {"high_yield_spread", "investment_grade_spread", "vix", "credit_stress_status"},
    "rate_pressure": {"dgs2", "dgs10", "dgs30", "dgs30_distance_to_5pct"},
    "real_yield_pressure": {"dfii10", "t10yie", "real_yield_pressure_status"},
    "inflation_energy_pressure": {
        "core_cpi_yoy",
        "core_pce_yoy",
        "ppiaco_yoy",
        "ppi_final_demand",
        "ppi_final_demand_yoy",
        "wti_30d_change",
        "brent_30d_change",
    },
    "equity_trend": {
        "sp500_30d_return",
        "nasdaq100_30d_return",
        "nasdaq_vs_sp500_30d",
    },
    "breadth_concentration_proxy": {
        "spy_proxy_30d_return",
        "rsp_proxy_30d_return",
        "qqq_proxy_30d_return",
        "spy_vs_rsp_30d",
        "qqq_vs_spy_30d",
        "hyg_vs_lqd_30d",
    },
    "market_stress_derived": {
        "sp500_drawdown_3m",
        "nasdaq100_drawdown_3m",
        "dgs10_dgs2_curve_slope",
        "dgs30_dgs10_curve_slope",
        "tlt_vs_shy_30d",
    },
    "portfolio_deviation": {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
    },
}
METRIC_SPECS = {
    "credit_stress": [
        ("high_yield_spread", "High-yield spread", "percent", "percent", "missing"),
        (
            "investment_grade_spread",
            "Investment-grade spread",
            "percent",
            "percent",
            "missing",
        ),
        ("vix", "VIX", "index", "number", "missing"),
        ("credit_stress_status", "Credit stress status", None, "text", "missing"),
    ],
    "rate_pressure": [
        ("dgs2", "2Y Treasury yield", "percent", "percent", "missing"),
        ("dgs10", "10Y Treasury yield", "percent", "percent", "missing"),
        ("dgs30", "30Y Treasury yield", "percent", "percent", "missing"),
        (
            "dgs30_distance_to_5pct",
            "30Y distance to 5%",
            "pp",
            "pp",
            "missing",
        ),
        ("dgs10_5d_avg", "10Y 5D average", "percent", "percent", "insufficient_history"),
        (
            "dgs30_breakout_confirmed",
            "30Y breakout confirmed",
            None,
            "bool",
            "research_needed",
        ),
    ],
    "real_yield_pressure": [
        ("dfii10", "10Y real yield", "percent", "percent", "missing"),
        ("t10yie", "10Y breakeven inflation", "percent", "percent", "missing"),
        ("real_yield_pressure_status", "Real yield pressure status", None, "text", "missing"),
    ],
    "inflation_energy_pressure": [
        ("core_cpi_yoy", "Core CPI YoY", "percent", "signed_percent", "missing"),
        ("core_pce_yoy", "Core PCE YoY", "percent", "signed_percent", "missing"),
        ("ppiaco_yoy", "PPIACO YoY", "percent", "signed_percent", "missing"),
        ("ppi_final_demand", "PPI final demand", "index", "number", "missing"),
        (
            "ppi_final_demand_yoy",
            "PPI final demand YoY",
            "percent",
            "signed_percent",
            "insufficient_history",
        ),
        ("wti_30d_change", "WTI 30D change", "percent", "signed_percent", "insufficient_history"),
        ("brent_30d_change", "Brent 30D change", "percent", "signed_percent", "insufficient_history"),
    ],
    "equity_trend": [
        ("sp500_30d_return", "S&P 500 30D return", "percent", "signed_percent", "insufficient_history"),
        ("sp500_60d_return", "S&P 500 60D return", "percent", "signed_percent", "insufficient_history"),
        (
            "nasdaq100_30d_return",
            "Nasdaq 100 30D return",
            "percent",
            "signed_percent",
            "insufficient_history",
        ),
        (
            "nasdaq100_60d_return",
            "Nasdaq 100 60D return",
            "percent",
            "signed_percent",
            "insufficient_history",
        ),
        ("nasdaq_vs_sp500_30d", "Nasdaq vs S&P 500 30D", "pp", "pp", "insufficient_history"),
    ],
    "breadth_concentration_proxy": [
        ("spy_proxy_30d_return", "SPY proxy 30D return", "percent", "signed_percent", "insufficient_history"),
        ("spy_proxy_60d_return", "SPY proxy 60D return", "percent", "signed_percent", "insufficient_history"),
        ("rsp_proxy_30d_return", "RSP proxy 30D return", "percent", "signed_percent", "insufficient_history"),
        ("rsp_proxy_60d_return", "RSP proxy 60D return", "percent", "signed_percent", "insufficient_history"),
        ("qqq_proxy_30d_return", "QQQ proxy 30D return", "percent", "signed_percent", "insufficient_history"),
        ("qqq_proxy_60d_return", "QQQ proxy 60D return", "percent", "signed_percent", "insufficient_history"),
        ("spy_vs_rsp_30d", "SPY vs RSP 30D", "pp", "pp", "insufficient_history"),
        ("spy_vs_rsp_60d", "SPY vs RSP 60D", "pp", "pp", "insufficient_history"),
        ("qqq_vs_spy_30d", "QQQ vs SPY 30D", "pp", "pp", "insufficient_history"),
        ("qqq_vs_spy_60d", "QQQ vs SPY 60D", "pp", "pp", "insufficient_history"),
        ("hyg_vs_lqd_30d", "HYG vs LQD 30D", "pp", "pp", "insufficient_history"),
        ("hyg_vs_lqd_60d", "HYG vs LQD 60D", "pp", "pp", "insufficient_history"),
    ],
    "market_stress_derived": [
        ("sp500_drawdown_3m", "S&P 500 3M drawdown", "percent", "signed_percent", "insufficient_history"),
        ("sp500_drawdown_6m", "S&P 500 6M drawdown", "percent", "signed_percent", "insufficient_history"),
        ("nasdaq100_drawdown_3m", "Nasdaq 100 3M drawdown", "percent", "signed_percent", "insufficient_history"),
        ("nasdaq100_drawdown_6m", "Nasdaq 100 6M drawdown", "percent", "signed_percent", "insufficient_history"),
        ("dgs10_dgs2_curve_slope", "10Y-2Y curve slope", "pp", "pp", "insufficient_history"),
        ("dgs30_dgs10_curve_slope", "30Y-10Y curve slope", "pp", "pp", "insufficient_history"),
        ("tlt_proxy_30d_return", "TLT proxy 30D return", "percent", "signed_percent", "insufficient_history"),
        ("gld_proxy_30d_return", "GLD proxy 30D return", "percent", "signed_percent", "insufficient_history"),
        ("shy_proxy_30d_return", "SHY proxy 30D return", "percent", "signed_percent", "insufficient_history"),
        ("tlt_vs_shy_30d", "TLT vs SHY 30D", "pp", "pp", "insufficient_history"),
    ],
    "portfolio_deviation": [
        ("max_deviation_asset", "Max deviation asset", None, "text", "missing"),
        ("max_deviation_pp", "Max deviation", "pp", "pp", "missing"),
        ("equity_total_deviation_pp", "Equity total deviation", "pp", "pp", "missing"),
        ("cash_reserve_status", "Cash reserve status", None, "text", "missing"),
        ("holdings_updated_at", "Holdings updated at", None, "text", "missing"),
    ],
}
PORTFOLIO_TARGET_ASSET_CLASSES = ("sp500", "nasdaq100", "short_bond", "gold")
PORTFOLIO_DEFAULT_TARGET_WEIGHTS = {
    "sp500": 0.50,
    "nasdaq100": 0.20,
    "short_bond": 0.20,
    "gold": 0.10,
}
PORTFOLIO_COMPACT_INTERPRETATION_HINT = (
    "Cash reserve excluded from target allocation; portfolio deviation is not "
    "attributed to market factors; no trading instruction."
)


@dataclass(frozen=True)
class ReportState:
    name: str
    path: Path
    exists: bool
    data: dict[str, Any] | None = None
    error_summary: str | None = None


@dataclass(frozen=True)
class PortfolioDeviationCompact:
    generated_at: str | None
    holdings_updated_at: str | None
    target_weights: dict[str, float]
    current_weights: dict[str, float]
    deviation_pp: dict[str, float]
    max_deviation_asset: str | None
    max_deviation_pp: float | None
    equity_total_current_weight: float | None
    equity_total_target_weight: float | None
    equity_total_deviation_pp: float | None
    cash_reserve_status: str
    stale_status: str
    notes: list[str]


def build_dashboard_summary(
    reports_dir: Path | str | None = None,
    market_history_db_path: Path | str | None = None,
) -> DashboardSummaryResponse:
    base_dir = Path(reports_dir) if reports_dir is not None else DEFAULT_REPORTS_DIR
    dashboard_market_history_db_path = _dashboard_market_history_db_path(
        base_dir,
        market_history_db_path,
    )
    reports = _load_dashboard_reports(base_dir)
    provider_health = _provider_health_summary(
        base_dir / REPORT_FILES["provider_health"]
    )
    modules = _build_modules(reports, market_history_db_path=dashboard_market_history_db_path)
    missing_data = _missing_data(reports)
    data_freshness = _data_freshness(reports, provider_health)
    next_actions = _next_actions(modules, provider_health)

    return DashboardSummaryResponse(
        generated_at=_first_generated_at(reports, provider_health),
        overall_status=_overall_status(modules, provider_health),
        overall_risk_level=_overall_risk_level(reports),
        modules=modules,
        provider_health=provider_health,
        missing_data=missing_data,
        data_freshness=data_freshness,
        next_actions=next_actions,
    )


def build_dashboard_evidence_table(
    reports_dir: Path | str | None = None,
    market_history_db_path: Path | str | None = None,
    module: str | None = None,
    status: str | None = None,
    source_badge: str | None = None,
    ai_context_allowed: bool | None = None,
    write_last_good: bool = True,
) -> DashboardEvidenceTableResponse:
    base_dir = Path(reports_dir) if reports_dir is not None else DEFAULT_REPORTS_DIR
    summary = build_dashboard_summary(
        reports_dir=reports_dir,
        market_history_db_path=market_history_db_path,
    )
    reports = _load_dashboard_reports(base_dir)
    dashboard_market_history_db_path = _dashboard_market_history_db_path(
        base_dir,
        market_history_db_path,
    )
    all_rows = _evidence_rows_from_summary(summary) + _labor_macro_evidence_rows(
        reports,
        db_path=dashboard_market_history_db_path,
    )
    if write_last_good and _last_good_write_allowed(reports_dir):
        _save_last_good_candidates(all_rows)
    filtered_rows = [
        row
        for row in all_rows
        if _evidence_row_matches(
            row,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        )
    ]

    return DashboardEvidenceTableResponse(
        generated_at=summary.generated_at,
        overall_status=summary.overall_status,
        row_count=len(filtered_rows),
        modules=sorted({row.module for row in all_rows}),
        rows=filtered_rows,
        filters=_evidence_filters(
            all_rows,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        ),
        next_actions=summary.next_actions,
    )


def _load_dashboard_reports(base_dir: Path) -> dict[str, ReportState]:
    reports = {
        key: _load_report(key, base_dir / file_name)
        for key, file_name in REPORT_FILES.items()
    }
    for key, file_name in OPTIONAL_METADATA_REPORT_FILES.items():
        path = base_dir / file_name
        if path.exists():
            reports[key] = _load_report(key, path)
    return reports


def _load_report(name: str, path: Path) -> ReportState:
    if not path.exists():
        return ReportState(name=name, path=path, exists=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ReportState(
            name=name,
            path=path,
            exists=True,
            error_summary=f"{path.name} is invalid or unreadable",
        )
    if not isinstance(payload, dict):
        return ReportState(
            name=name,
            path=path,
            exists=True,
            error_summary=f"{path.name} is not a JSON object",
        )
    return ReportState(name=name, path=path, exists=True, data=payload)


def _dashboard_market_history_db_path(
    reports_dir: Path,
    market_history_db_path: Path | str | None,
) -> Path | str:
    if market_history_db_path is not None:
        return market_history_db_path
    default_path = market_history_store.get_default_market_history_db_path()
    if Path(DEFAULT_MARKET_HISTORY_DB_PATH) != default_path:
        return DEFAULT_MARKET_HISTORY_DB_PATH
    try:
        if reports_dir.resolve() == PROJECT_REPORTS_DIR.resolve():
            return DEFAULT_MARKET_HISTORY_DB_PATH
    except OSError:
        pass
    return reports_dir / "market_history.sqlite3"


def _evidence_rows_from_summary(
    summary: DashboardSummaryResponse,
) -> list[DashboardEvidenceRow]:
    rows: list[DashboardEvidenceRow] = []
    for module_key, module in summary.modules.items():
        for metric in module.key_metrics:
            rows.append(_evidence_row(module_key, metric))
    return rows


def _labor_macro_evidence_rows(
    reports: dict[str, ReportState],
    *,
    db_path: Path | str | None = None,
) -> list[DashboardEvidenceRow]:
    market = reports["market_snapshot"]
    llm_context = reports.get("llm_context_pack")
    metric_reports = (market, llm_context) if llm_context else (market,)
    metrics = [
        _build_metric("labor_macro", metric_reports, spec)
        for spec in LABOR_METRIC_SPECS
    ]
    metrics = _apply_historical_derived_metrics(
        metrics,
        module_key="labor_macro",
        metric_keys=LABOR_HISTORICAL_DERIVED_METRIC_KEYS,
        hint_suffix="",
        fallback_source="market_history",
        required_dependency_source_badges={"official"},
        replace_existing=True,
        db_path=db_path,
    )
    return [_evidence_row("labor_macro", metric) for metric in metrics]


def _evidence_row(module_key: str, metric: DashboardMetric) -> DashboardEvidenceRow:
    ai_context_allowed = _evidence_ai_context_allowed(metric)
    blocked_reason = _ppi_observation_date_blocked_reason(metric)
    if blocked_reason is not None:
        ai_context_allowed = False
    return DashboardEvidenceRow(
        row_id=f"{module_key}:{metric.metric_key}",
        module=module_key,
        metric_key=metric.metric_key,
        display_name=metric.display_name,
        value=metric.value,
        value_text=_evidence_value_text(metric),
        unit=metric.unit,
        status=metric.status,
        source=metric.source,
        source_badge=metric.source_badge,
        source_series=metric.source_series,
        observation_date=metric.observation_date,
        generated_at=metric.generated_at,
        freshness_status=metric.freshness_status,
        missing_reason=metric.missing_reason,
        interpretation_hint=metric.interpretation_hint,
        blocked_reason=None
        if ai_context_allowed
        else blocked_reason or _ai_context_blocked_reason(
            status=metric.status,
            value=metric.value,
            source=metric.source,
            source_badge=metric.source_badge,
            observation_date=metric.observation_date,
            generated_at=metric.generated_at,
            freshness_status=metric.freshness_status,
            interpretation_hint=metric.interpretation_hint,
        ),
        ai_context_allowed=ai_context_allowed,
    )


def _last_good_write_allowed(reports_dir: Path | str | None) -> bool:
    return reports_dir is None and Path(DEFAULT_REPORTS_DIR) == PROJECT_REPORTS_DIR


def _save_last_good_candidates(rows: list[DashboardEvidenceRow]) -> None:
    for row in rows:
        if row.module == "portfolio_deviation":
            continue
        if not row.ai_context_allowed:
            continue
        try:
            last_good_cache.save_last_good(row)
        except (OSError, ValueError):
            continue


def _evidence_value_text(metric: DashboardMetric) -> str:
    text = str(metric.value_text or "").strip()
    if text and text != "--":
        return text
    return _missing_value_text(metric.status)


def _evidence_ai_context_allowed(metric: DashboardMetric) -> bool:
    if _ppi_observation_date_blocked_reason(metric) is not None:
        return False
    return _ai_context_allowed(
        status=metric.status,
        source=metric.source,
        source_badge=metric.source_badge,
        observation_date=metric.observation_date,
        generated_at=metric.generated_at,
        freshness_status=metric.freshness_status,
        interpretation_hint=metric.interpretation_hint,
    ) and bool(metric.ai_context_allowed)


def _ppi_observation_date_blocked_reason(metric: DashboardMetric) -> str | None:
    if metric.metric_key in {"ppi_final_demand", "ppi_final_demand_yoy"} and not metric.observation_date:
        return "observation_date_missing"
    return None


def _evidence_row_matches(
    row: DashboardEvidenceRow,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> bool:
    if module is not None and row.module != module:
        return False
    if status is not None and row.status != status:
        return False
    if source_badge is not None and row.source_badge != source_badge:
        return False
    if ai_context_allowed is not None and row.ai_context_allowed != ai_context_allowed:
        return False
    return True


def _evidence_filters(
    rows: list[DashboardEvidenceRow],
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> dict[str, Any]:
    return {
        "available": {
            "modules": sorted({row.module for row in rows}),
            "statuses": sorted({row.status for row in rows}),
            "source_badges": sorted({row.source_badge for row in rows}),
            "ai_context_allowed": sorted({row.ai_context_allowed for row in rows}),
        },
        "applied": {
            "module": module,
            "status": status,
            "source_badge": source_badge,
            "ai_context_allowed": ai_context_allowed,
        },
    }


def _provider_health_summary(health_path: Path) -> dict:
    response = provider_service.build_provider_health(health_path)
    payload = _model_to_dict(response)
    return {
        "generated_at": payload.get("generated_at"),
        "overall_status": payload.get("overall_status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "checks": payload.get("checks") if isinstance(payload.get("checks"), list) else [],
        "next_action": payload.get("next_action"),
        "error_summary": payload.get("error_summary"),
    }


def _build_modules(
    reports: dict[str, ReportState],
    *,
    market_history_db_path: Path | str | None = None,
) -> dict[str, DashboardModule]:
    market = reports["market_snapshot"]
    temperature = reports["market_temperature"]
    portfolio = reports["portfolio_snapshot"]
    llm_context = reports.get("llm_context_pack")
    market_metadata_reports = (market, llm_context) if llm_context else (market,)
    market_temperature_metadata_reports = (
        market,
        temperature,
        llm_context,
    ) if llm_context else (market, temperature)
    return {
        "credit_stress": _market_module(
            key="credit_stress",
            label="credit stress",
            reports=market_temperature_metadata_reports,
            signal_terms=("financial_conditions", "high_yield_spread", "credit", "vix"),
            key_metrics=_key_metrics_for_module("credit_stress", market_temperature_metadata_reports),
        ),
        "rate_pressure": _market_module(
            key="rate_pressure",
            label="rate pressure",
            reports=market_metadata_reports,
            signal_terms=("dgs10", "dgs30", "treasury_yields", "10y", "30y"),
            key_metrics=_key_metrics_for_module("rate_pressure", market_metadata_reports),
        ),
        "real_yield_pressure": _market_module(
            key="real_yield_pressure",
            label="real yield pressure",
            reports=market_metadata_reports,
            signal_terms=("real_yield_10y", "dfii10", "real_yield"),
            key_metrics=_key_metrics_for_module("real_yield_pressure", market_metadata_reports),
        ),
        "inflation_energy_pressure": _market_module(
            key="inflation_energy_pressure",
            label="inflation and energy pressure",
            reports=market_temperature_metadata_reports,
            signal_terms=("cpi", "pce", "ppi", "oil", "energy", "inflation"),
            key_metrics=_key_metrics_for_module(
                "inflation_energy_pressure",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
        ),
        "equity_trend": _market_module(
            key="equity_trend",
            label="equity trend",
            reports=market_temperature_metadata_reports,
            signal_terms=("sp500", "nasdaq", "nasdaq100", "equity_temperature", "equity"),
            key_metrics=_key_metrics_for_module(
                "equity_trend",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
        ),
        "breadth_concentration_proxy": _market_module(
            key="breadth_concentration_proxy",
            label="proxy breadth and concentration",
            reports=market_temperature_metadata_reports,
            signal_terms=("breadth", "concentration", "spy_proxy", "rsp_proxy", "qqq_proxy"),
            key_metrics=_key_metrics_for_module(
                "breadth_concentration_proxy",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
        ),
        "market_stress_derived": _market_module(
            key="market_stress_derived",
            label="market stress derived",
            reports=market_temperature_metadata_reports,
            signal_terms=("drawdown", "curve", "tlt_proxy", "gld_proxy", "shy_proxy"),
            key_metrics=_key_metrics_for_module(
                "market_stress_derived",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
        ),
        "portfolio_deviation": _portfolio_module(portfolio),
    }


def _market_module(
    key: str,
    label: str,
    reports: tuple[ReportState, ...],
    signal_terms: tuple[str, ...],
    key_metrics: list[DashboardMetric],
) -> DashboardModule:
    error = _first_error(reports)
    if error is not None:
        return _module(
            key=key,
            status="error",
            label=label,
            summary=f"{label} report data is invalid",
            source_badge="report_error",
            error_summary=error,
            key_metrics=key_metrics,
        )

    available_reports = [report for report in reports if report.data is not None]
    if key == "equity_trend" and _equity_historical_derived_metrics_available(key_metrics):
        return _module(
            key=key,
            status="ok",
            label=label,
            summary=(
                "equity trend historical derived metrics available; risk "
                "interpretation remains descriptive"
            ),
            source_badge="derived",
            updated_at=_latest_metric_generated_at(key_metrics),
            key_metrics=key_metrics,
        )
    if key == "breadth_concentration_proxy" and _proxy_historical_derived_metrics_available(key_metrics):
        return _module(
            key=key,
            status="ok",
            label=label,
            summary=(
                "proxy breadth and concentration metrics available; yfinance ETF "
                "proxy boundary applies"
            ),
            source_badge="derived",
            updated_at=_latest_metric_generated_at(key_metrics),
            key_metrics=key_metrics,
        )
    if key == "market_stress_derived" and _market_stress_historical_derived_metrics_available(key_metrics):
        return _module(
            key=key,
            status="ok",
            label=label,
            summary=(
                "local drawdown, curve slope, and cross-asset proxy metrics "
                "available; descriptive boundaries apply"
            ),
            source_badge="derived",
            updated_at=_latest_metric_generated_at(key_metrics),
            key_metrics=key_metrics,
        )
    if not available_reports:
        return _module(
            key=key,
            status="missing",
            label=label,
            summary=f"{label} data missing",
            source_badge="missing_report",
            next_action=_run_reports_action(),
            key_metrics=key_metrics,
        )

    if any(_contains_signal(report.data, signal_terms) for report in available_reports):
        status = _coerce_status(_first_status(available_reports), default="ok")
        return _module(
            key=key,
            status=status,
            label=label,
            summary=f"{label} compact data available",
            source_badge="cached_report",
            updated_at=_first_updated_at(available_reports),
            key_metrics=key_metrics,
        )

    return _module(
        key=key,
        status="missing",
        label=label,
        summary=f"{label} compact signal missing",
        source_badge="cached_report",
        updated_at=_first_updated_at(available_reports),
        next_action=_run_reports_action(),
        key_metrics=key_metrics,
    )


def _portfolio_module(report: ReportState) -> DashboardModule:
    key_metrics = _key_metrics_for_module("portfolio_deviation", (report,))
    if report.error_summary is not None:
        return _module(
            key="portfolio_deviation",
            status="error",
            label="portfolio deviation",
            summary="portfolio snapshot invalid",
            source_badge="report_error",
            error_summary=report.error_summary,
            key_metrics=key_metrics,
        )
    if report.data is None:
        return _module(
            key="portfolio_deviation",
            status="missing",
            label="missing",
            summary="portfolio snapshot missing",
            source_badge="missing_report",
            next_action="python scripts/run_portfolio_check.py",
            key_metrics=key_metrics,
        )
    compact = _portfolio_deviation_compact(report)
    if compact is not None:
        return _module(
            key="portfolio_deviation",
            status=_portfolio_compact_module_status(compact),
            label="compact",
            summary="portfolio deviation compact data available",
            source_badge="cached_report",
            updated_at=compact.generated_at,
            key_metrics=key_metrics,
        )
    return _module(
        key="portfolio_deviation",
        status=_coerce_status(report.data.get("status"), default="ok"),
        label="available",
        summary="portfolio snapshot available",
        source_badge="cached_report",
        updated_at=_string_or_none(
            report.data.get("generated_at") or report.data.get("updated_at")
        ),
        key_metrics=key_metrics,
    )


def _module(
    key: str,
    status: str,
    label: str | None,
    summary: str | None,
    source_badge: str | None,
    updated_at: str | None = None,
    next_action: str | None = None,
    error_summary: str | None = None,
    key_metrics: list[DashboardMetric] | None = None,
) -> DashboardModule:
    metrics = key_metrics or []
    coerced_status = _coerce_status(status)
    adjusted_status, coverage_note = _module_status_with_coverage(
        key,
        coerced_status,
        metrics,
    )
    adjusted_summary = _summary_with_coverage_note(summary, coverage_note)
    return DashboardModule(
        key=key,
        status=adjusted_status,
        label=label,
        summary=adjusted_summary,
        source_badge=source_badge,
        updated_at=updated_at,
        next_action=next_action,
        error_summary=_safe_error_summary(error_summary),
        key_metrics=metrics,
    )


def _key_metrics_for_module(
    module_key: str,
    reports: tuple[ReportState, ...],
    *,
    market_history_db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    metrics = [
        _build_metric(module_key, reports, spec)
        for spec in METRIC_SPECS.get(module_key, [])
    ]
    if module_key == "equity_trend":
        return _apply_historical_derived_metrics(
            metrics,
            module_key="equity_trend",
            metric_keys=EQUITY_HISTORICAL_DERIVED_METRIC_KEYS,
            hint_suffix=EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX,
            fallback_source="local_market_history",
            db_path=market_history_db_path,
        )
    if module_key == "inflation_energy_pressure":
        metrics = _apply_ppi_final_demand_history(
            metrics,
            db_path=market_history_db_path,
        )
        metrics = _apply_historical_derived_metrics(
            metrics,
            module_key="inflation_energy_pressure",
            metric_keys=OIL_HISTORICAL_DERIVED_METRIC_KEYS,
            hint_suffix=OIL_HISTORICAL_DERIVED_HINT_SUFFIX,
            fallback_source="local_market_history",
            required_dependency_source_badges={"official"},
            replace_existing=True,
            db_path=market_history_db_path,
        )
        return _apply_historical_derived_metrics(
            metrics,
            module_key="inflation_energy_pressure",
            metric_keys=PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS,
            hint_suffix="",
            fallback_source="local_market_history",
            required_dependency_source_badges={"official"},
            replace_existing=True,
            db_path=market_history_db_path,
        )
    if module_key == "breadth_concentration_proxy":
        return _apply_historical_derived_metrics(
            metrics,
            module_key="breadth_concentration_proxy",
            metric_keys=PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS,
            hint_suffix="",
            fallback_source="local_market_history",
            required_dependency_source_badges={"proxy"},
            db_path=market_history_db_path,
        )
    if module_key == "market_stress_derived":
        return _apply_historical_derived_metrics(
            metrics,
            module_key="market_stress_derived",
            metric_keys=MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS,
            hint_suffix="",
            fallback_source="local_market_history",
            fallback_observations=_compact_dgs_fallback_observations(reports),
            db_path=market_history_db_path,
        )
    return metrics


def _build_metric(
    module_key: str,
    reports: tuple[ReportState, ...],
    spec: tuple[str, str, str | None, str, str],
) -> DashboardMetric:
    metric_key, display_name, unit, format_kind, missing_status = spec
    derived = _derived_metric(metric_key, reports)
    if derived is not None:
        return derived
    compact = _portfolio_compact_metric(
        module_key=module_key,
        reports=reports,
        metric_key=metric_key,
        display_name=display_name,
        unit=unit,
        format_kind=format_kind,
    )
    if compact is not None:
        return compact

    found = _find_metric(metric_key, reports)
    official_macro = official_macro_pack.get_official_macro_metric(metric_key)
    interpretation_hint = _interpretation_hint(metric_key)
    if found is None:
        return _missing_metric(
            metric_key=metric_key,
            display_name=display_name,
            unit=unit,
            status=official_macro.status_when_missing if official_macro else missing_status,
            generated_at=_first_updated_at([report for report in reports if report.data is not None]),
            interpretation_hint=interpretation_hint,
            source=official_macro.source if official_macro else None,
            source_badge=(
                official_macro.source_badge
                if official_macro and official_macro.source_badge == "research_needed"
                else None
            ),
            missing_reason=official_macro.missing_reason if official_macro else None,
        )

    value, payload, report = found
    interpretation_hint = _metric_interpretation_hint(metric_key, payload)
    quality_metadata = _metric_quality_metadata(report, metric_key) or _first_metric_quality_metadata(reports, metric_key)
    status = _metric_status(payload)
    if (
        official_macro
        and official_macro.source_series
        and status == "research_needed"
        and official_macro.status_when_missing != "research_needed"
    ):
        status = official_macro.status_when_missing
    freshness_status = _metric_freshness(
        payload,
        report,
        metric_key=metric_key,
        quality_metadata=quality_metadata,
    )
    if freshness_status == "stale" and status == "ok":
        status = "stale"

    source = _metric_source(payload, report, quality_metadata)
    source_series = _metric_source_series(payload, quality_metadata, official_macro)
    source_badge = _metric_source_badge(payload, report, module_key, metric_key, quality_metadata)
    if (
        official_macro
        and official_macro.source_series
        and status in AI_BLOCKED_METRIC_STATUSES
        and status != "research_needed"
    ):
        source_badge = "missing"
    if official_macro and source is None and source_badge == "missing":
        source = official_macro.source
        source_badge = official_macro.source_badge
    if official_macro and source_badge == "missing":
        source_badge = official_macro.source_badge
    if official_macro and source is None:
        source = official_macro.source
    if (
        official_macro
        and official_macro.source_series
        and value is None
        and status in AI_BLOCKED_METRIC_STATUSES
        and status != "research_needed"
    ):
        source_badge = "missing"
    observation_date = _metric_observation_date(payload, quality_metadata)
    generated_at = _metric_generated_at(payload, report)
    missing_reason = _string_or_none(payload.get("missing_reason")) if isinstance(payload, dict) else None
    yoy_result = _normalize_inflation_yoy_value(metric_key, value, payload)
    if yoy_result == "index_level":
        return DashboardMetric(
            metric_key=metric_key,
            display_name=display_name,
            value=None,
            value_text=_missing_value_text("insufficient_history"),
            unit=unit,
            status="insufficient_history",
            source=source,
            source_badge="missing",
            source_series=source_series,
            observation_date=None,
            generated_at=generated_at,
            freshness_status="insufficient_history",
            missing_reason=INDEX_LEVEL_YOY_MISSING_REASON,
            interpretation_hint=interpretation_hint,
            ai_context_allowed=False,
        )
    if isinstance(yoy_result, float):
        value = yoy_result
    if official_macro and status in AI_BLOCKED_METRIC_STATUSES and missing_reason is None:
        missing_reason = official_macro.missing_reason

    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=_format_value(value, format_kind, status),
        unit=unit,
        status=status,
        source=source,
        source_badge=source_badge,
        source_series=source_series,
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=missing_reason,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=_ai_context_allowed(
            status=status,
            source=source,
            source_badge=source_badge,
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=interpretation_hint,
        )
        and not (
            metric_key in {"ppi_final_demand", "ppi_final_demand_yoy"}
            and not observation_date
        ),
    )


def _apply_historical_derived_metrics(
    metrics: list[DashboardMetric],
    *,
    module_key: str,
    metric_keys: set[str],
    hint_suffix: str,
    fallback_source: str,
    fallback_observations: dict[str, dict[str, Any]] | None = None,
    required_dependency_source_badges: set[str] | None = None,
    replace_existing: bool = False,
    db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    target_db_path = db_path if db_path is not None else DEFAULT_MARKET_HISTORY_DB_PATH
    candidates = {
        item.metric_key: item
        for item in historical_derived_metrics.build_historical_dashboard_candidates(
            db_path=target_db_path,
            fallback_observations=fallback_observations,
        ).get(module_key, [])
        if item.metric_key in metric_keys
    }
    return [
        _historical_derived_metric(
            metric,
            candidates.get(metric.metric_key),
            metric_keys=metric_keys,
            hint_suffix=hint_suffix,
            fallback_source=fallback_source,
            required_dependency_source_badges=required_dependency_source_badges,
            replace_existing=replace_existing,
        )
        for metric in metrics
    ]


def _apply_ppi_final_demand_history(
    metrics: list[DashboardMetric],
    *,
    db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    target_db_path = db_path if db_path is not None else DEFAULT_MARKET_HISTORY_DB_PATH
    latest = _latest_ppifis_observation(target_db_path)
    if latest is None:
        return metrics
    return [
        _ppi_final_demand_history_metric(metric, latest)
        if metric.metric_key == "ppi_final_demand"
        else metric
        for metric in metrics
    ]


def _latest_ppifis_observation(db_path: Path | str | None) -> dict[str, Any] | None:
    rows = market_history_store.list_market_observations(
        metric_key="ppi_final_demand",
        limit=100,
        db_path=db_path,
    )
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("source_badge") != "official":
            continue
        if row.get("provider") != "FRED":
            continue
        if row.get("source_series") != "PPIFIS":
            continue
        if row.get("value_numeric") is None:
            continue
        return row
    return None


def _ppi_final_demand_history_metric(
    original: DashboardMetric,
    observation: dict[str, Any],
) -> DashboardMetric:
    official_macro = official_macro_pack.get_official_macro_metric("ppi_final_demand")
    interpretation_hint = (
        official_macro.interpretation_hint
        if official_macro
        else (
            "PPI Final Demand is the official headline final demand PPI index relayed "
            "by FRED PPIFIS; it is distinct from PPIACO and not consensus surprise data."
        )
    )
    value = float(observation["value_numeric"])
    generated_at = _string_or_none(observation.get("generated_at"))
    freshness_status = str(observation.get("freshness_status") or "historical")
    ai_context_allowed = bool(observation.get("ai_context_allowed")) and _ai_context_allowed(
        status="ok",
        source="FRED",
        source_badge="official",
        observation_date=_string_or_none(observation.get("observation_date")),
        generated_at=generated_at,
        freshness_status=freshness_status,
        interpretation_hint=interpretation_hint,
    )
    return DashboardMetric(
        metric_key=original.metric_key,
        display_name=original.display_name,
        value=value,
        value_text=_format_value(value, "number", "ok"),
        unit=original.unit,
        status="ok",
        source="FRED",
        source_badge="official",
        source_series="PPIFIS",
        observation_date=_string_or_none(observation.get("observation_date")),
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=ai_context_allowed,
    )


def _historical_derived_metric(
    original: DashboardMetric,
    candidate: historical_derived_metrics.HistoricalDerivedMetric | None,
    *,
    metric_keys: set[str],
    hint_suffix: str,
    fallback_source: str,
    required_dependency_source_badges: set[str] | None,
    replace_existing: bool,
) -> DashboardMetric:
    if original.metric_key not in metric_keys:
        return original
    if original.status != "insufficient_history" and not replace_existing:
        return original
    if candidate is None:
        return original
    if candidate.status in {"missing", "insufficient_history"}:
        if original.metric_key != "labor_deterioration_status":
            return original
        return DashboardMetric(
            metric_key=original.metric_key,
            display_name=original.display_name,
            value=None,
            value_text=candidate.value_text,
            unit=original.unit,
            status=candidate.status,
            source=fallback_source,
            source_badge="derived",
            source_series=", ".join(candidate.dependency_source_series or []) or None,
            observation_date=candidate.observation_date,
            generated_at=candidate.generated_at,
            freshness_status=candidate.freshness_status,
            missing_reason=candidate.missing_reason,
            interpretation_hint=candidate.interpretation_hint,
            ai_context_allowed=False,
        )
    if candidate.status not in {"ok", "watch", "pressure"} or candidate.value is None:
        return original
    if required_dependency_source_badges is not None:
        source_badges = set(candidate.dependency_source_badges or [])
        if not source_badges or not source_badges.issubset(required_dependency_source_badges):
            return original
    value = _dashboard_historical_derived_value(candidate)
    hint = _dashboard_historical_derived_hint(candidate, hint_suffix=hint_suffix)
    ai_context_allowed = bool(candidate.ai_context_allowed) and _ai_context_allowed(
        status=candidate.status,
        source=fallback_source,
        source_badge="derived",
        observation_date=candidate.observation_date,
        generated_at=candidate.generated_at,
        freshness_status=candidate.freshness_status,
        interpretation_hint=hint,
    )
    return DashboardMetric(
        metric_key=original.metric_key,
        display_name=original.display_name,
        value=value,
        value_text=_format_historical_derived_value(value, candidate.unit),
        unit=original.unit,
        status="ok",
        source=fallback_source,
        source_badge="derived",
        source_series=", ".join(candidate.dependency_source_series or []) or None,
        observation_date=candidate.observation_date,
        generated_at=candidate.generated_at,
        freshness_status=candidate.freshness_status,
        missing_reason=None,
        interpretation_hint=hint,
        ai_context_allowed=ai_context_allowed,
    )


def _compact_dgs_fallback_observations(
    reports: tuple[ReportState, ...],
) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for metric_key in ("dgs2", "dgs10", "dgs30"):
        found = _find_metric(metric_key, reports)
        if found is None:
            continue
        value, payload, report = found
        quality_metadata = _metric_quality_metadata(report, metric_key) or _first_metric_quality_metadata(reports, metric_key)
        official_macro = official_macro_pack.get_official_macro_metric(metric_key)
        numeric_value = _to_float(value)
        source_badge = _metric_source_badge(payload, report, "rate_pressure", metric_key, quality_metadata)
        source_series = _metric_source_series(payload, quality_metadata, official_macro=official_macro)
        if source_series is None and source_badge == "official" and metric_key in {"dgs2", "dgs10", "dgs30"}:
            source_series = metric_key.upper()
        observations[metric_key] = {
            "value": numeric_value if isinstance(numeric_value, float) else None,
            "source": _metric_source(payload, report, quality_metadata),
            "source_badge": source_badge,
            "source_series": source_series,
            "observation_date": _metric_observation_date(payload, quality_metadata),
            "generated_at": _metric_generated_at(payload, report),
            "freshness_status": _metric_freshness(
                payload,
                report,
                metric_key=metric_key,
                quality_metadata=quality_metadata,
            ),
            "ai_context_allowed": not _dependency_unusable(found),
        }
    return observations


def _dashboard_historical_derived_value(
    candidate: historical_derived_metrics.HistoricalDerivedMetric,
) -> float | str | bool:
    if isinstance(candidate.value, (str, bool)):
        return candidate.value
    value = float(candidate.value)
    if candidate.unit in {"percent", "pp"}:
        return value * 100.0
    return value


def _format_historical_derived_value(value: float | str | bool, unit: str | None) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if unit == "percent":
        return f"{value:+.2f}%"
    if unit == "pp":
        return f"{value:+.2f}pp"
    if unit == "raw_pp":
        return f"{value:+.2f}pp"
    if unit == "raw_percent":
        return f"{value:.2f}%"
    if unit == "claims":
        return f"{value:,.0f}"
    return f"{value:.4g}"


def _dashboard_historical_derived_hint(
    candidate: historical_derived_metrics.HistoricalDerivedMetric,
    *,
    hint_suffix: str,
) -> str:
    base = (candidate.interpretation_hint or "").strip()
    return (base + hint_suffix).strip()


def _equity_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return any(
        metric.metric_key in EQUITY_HISTORICAL_DERIVED_METRIC_KEYS
        and metric.status == "ok"
        and metric.source_badge == "derived"
        and metric.value is not None
        for metric in metrics
    )


def _proxy_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return any(
        metric.metric_key in PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS
        and metric.status == "ok"
        and metric.source_badge == "derived"
        and metric.value is not None
        for metric in metrics
    )


def _market_stress_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return any(
        metric.metric_key in MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS
        and metric.status == "ok"
        and metric.source_badge == "derived"
        and metric.value is not None
        for metric in metrics
    )


def _latest_metric_generated_at(metrics: list[DashboardMetric]) -> str | None:
    candidates = [
        value
        for metric in metrics
        for value in [metric.generated_at or metric.observation_date]
        if value
    ]
    return max(candidates) if candidates else None


def _portfolio_compact_metric(
    *,
    module_key: str,
    reports: tuple[ReportState, ...],
    metric_key: str,
    display_name: str,
    unit: str | None,
    format_kind: str,
) -> DashboardMetric | None:
    if module_key != "portfolio_deviation":
        return None
    report = next((item for item in reports if item.name == "portfolio_snapshot"), None)
    if report is None:
        return None
    compact = _portfolio_deviation_compact(report)
    if compact is None:
        return None
    value_map: dict[str, Any] = {
        "max_deviation_asset": compact.max_deviation_asset,
        "max_deviation_pp": compact.max_deviation_pp,
        "equity_total_deviation_pp": compact.equity_total_deviation_pp,
        "cash_reserve_status": compact.cash_reserve_status,
        "holdings_updated_at": compact.holdings_updated_at,
    }
    if metric_key not in value_map:
        return None

    value = value_map[metric_key]
    if value is None:
        return _missing_metric(
            metric_key=metric_key,
            display_name=display_name,
            unit=unit,
            status="missing",
            generated_at=compact.generated_at,
            interpretation_hint=PORTFOLIO_COMPACT_INTERPRETATION_HINT,
        )

    status = _portfolio_compact_metric_status(compact, metric_key)
    source = "local_portfolio_compact"
    source_badge = "local"
    observation_date = compact.holdings_updated_at
    freshness_status = compact.stale_status
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=_format_value(value, format_kind, status),
        unit=unit,
        status=status,
        source=source,
        source_badge=source_badge,
        observation_date=observation_date,
        generated_at=compact.generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=PORTFOLIO_COMPACT_INTERPRETATION_HINT,
        ai_context_allowed=_ai_context_allowed(
            status=status,
            source=source,
            source_badge=source_badge,
            observation_date=observation_date,
            generated_at=compact.generated_at,
            freshness_status=freshness_status,
            interpretation_hint=PORTFOLIO_COMPACT_INTERPRETATION_HINT,
        ),
    )


def _portfolio_deviation_compact(report: ReportState) -> PortfolioDeviationCompact | None:
    if not isinstance(report.data, dict):
        return None
    data = report.data
    embedded = data.get("portfolio_deviation_compact")
    compact_payload = embedded if isinstance(embedded, dict) else data

    target_weights = _portfolio_weight_map(
        compact_payload.get("target_weights")
        or compact_payload.get("target_allocation")
        or PORTFOLIO_DEFAULT_TARGET_WEIGHTS,
        default=PORTFOLIO_DEFAULT_TARGET_WEIGHTS,
    )
    current_weights = _portfolio_weight_map(
        compact_payload.get("current_weights") or compact_payload.get("weights_ex_cash")
    )
    deviation_pp = _portfolio_deviation_pp_map(compact_payload, current_weights, target_weights)
    if not current_weights and not deviation_pp:
        return None

    max_deviation_asset = _max_deviation_asset(deviation_pp)
    max_deviation_pp = (
        round(deviation_pp[max_deviation_asset], 4)
        if max_deviation_asset is not None
        else None
    )
    equity_current = _sum_weights(current_weights, ("sp500", "nasdaq100"))
    equity_target = _sum_weights(target_weights, ("sp500", "nasdaq100"))
    equity_deviation_pp = (
        round((equity_current - equity_target) * 100.0, 4)
        if equity_current is not None and equity_target is not None
        else None
    )
    holdings_updated_at = _portfolio_holdings_updated_at(data)
    generated_at = _string_or_none(
        compact_payload.get("generated_at")
        or data.get("generated_at")
        or data.get("updated_at")
    )
    stale_status = _portfolio_stale_status(
        holdings_updated_at=holdings_updated_at,
        generated_at=generated_at,
        existing_status=_string_or_none(
            compact_payload.get("stale_status")
            or data.get("holdings_freshness_status")
        ),
    )
    cash_reserve_status = _portfolio_cash_reserve_status(data)

    return PortfolioDeviationCompact(
        generated_at=generated_at,
        holdings_updated_at=holdings_updated_at,
        target_weights={key: round(value * 100.0, 4) for key, value in target_weights.items()},
        current_weights={key: round(value * 100.0, 4) for key, value in current_weights.items()},
        deviation_pp={key: round(value, 4) for key, value in deviation_pp.items()},
        max_deviation_asset=max_deviation_asset,
        max_deviation_pp=max_deviation_pp,
        equity_total_current_weight=round(equity_current * 100.0, 4)
        if equity_current is not None
        else None,
        equity_total_target_weight=round(equity_target * 100.0, 4)
        if equity_target is not None
        else None,
        equity_total_deviation_pp=equity_deviation_pp,
        cash_reserve_status=cash_reserve_status,
        stale_status=stale_status,
        notes=[
            "cash reserve excluded from target allocation",
            "portfolio deviation is not attributed to market factors",
            "no trading instruction",
        ],
    )


def _portfolio_weight_map(
    value: Any,
    default: dict[str, float] | None = None,
) -> dict[str, float]:
    payload = value if isinstance(value, dict) else {}
    result: dict[str, float] = {}
    for key in PORTFOLIO_TARGET_ASSET_CLASSES:
        number = _to_float(payload.get(key))
        if number is None and default is not None:
            number = default[key]
        if number is None:
            continue
        result[key] = _weight_fraction(number)
    return result


def _portfolio_deviation_pp_map(
    payload: dict[str, Any],
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> dict[str, float]:
    explicit = payload.get("deviation_pp")
    if isinstance(explicit, dict):
        return {
            key: number
            for key in PORTFOLIO_TARGET_ASSET_CLASSES
            if (number := _to_float(explicit.get(key))) is not None
        }
    fractional = payload.get("deviation")
    if isinstance(fractional, dict):
        return {
            key: round(_weight_fraction(number) * 100.0, 4)
            for key in PORTFOLIO_TARGET_ASSET_CLASSES
            if (number := _to_float(fractional.get(key))) is not None
        }
    return {
        key: round((current_weights[key] - target_weights[key]) * 100.0, 4)
        for key in PORTFOLIO_TARGET_ASSET_CLASSES
        if key in current_weights and key in target_weights
    }


def _weight_fraction(value: float) -> float:
    return value / 100.0 if abs(value) > 1.0 else value


def _max_deviation_asset(deviation_pp: dict[str, float]) -> str | None:
    if not deviation_pp:
        return None
    return max(deviation_pp, key=lambda key: abs(deviation_pp[key]))


def _sum_weights(weights: dict[str, float], keys: tuple[str, ...]) -> float | None:
    if not all(key in weights for key in keys):
        return None
    return sum(weights[key] for key in keys)


def _portfolio_holdings_updated_at(data: dict[str, Any]) -> str | None:
    value = data.get("holdings_updated_at")
    if isinstance(value, dict):
        value = value.get("value") or value.get("date") or value.get("updated_at")
    return _string_or_none(value)


def _portfolio_cash_reserve_status(data: dict[str, Any]) -> str:
    if "cash_reserve_status" in data:
        value = data["cash_reserve_status"]
        if isinstance(value, dict):
            value = value.get("value") or value.get("status")
        text = _string_or_none(value)
        if text in {
            "cash_excluded_from_target_allocation",
            "cash_missing",
            "cash_present",
            "unknown",
        }:
            return text
    if any(key in data for key in ("cash", "cash_reserve_value")):
        return "cash_excluded_from_target_allocation"
    return "cash_missing"


def _portfolio_stale_status(
    *,
    holdings_updated_at: str | None,
    generated_at: str | None,
    existing_status: str | None,
) -> str:
    holdings_date = _parse_date(holdings_updated_at)
    generated_date = _parse_date(generated_at)
    if holdings_date is not None and generated_date is not None:
        age_days = max((generated_date - holdings_date).days, 0)
        if age_days <= 14:
            return "fresh"
        if age_days <= 30:
            return "watch"
        return "stale"
    status = (existing_status or "").lower()
    if status in {"fresh", "ok"}:
        return "fresh"
    if status in {"watch", "aging"}:
        return "watch"
    if status in {"stale", "very_stale"}:
        return "stale"
    return "unknown"


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _portfolio_compact_metric_status(
    compact: PortfolioDeviationCompact,
    metric_key: str,
) -> str:
    if compact.stale_status == "stale":
        return "stale"
    if compact.stale_status == "unknown":
        return "unknown"
    if metric_key == "holdings_updated_at":
        return "ok" if compact.stale_status in {"fresh", "watch"} else compact.stale_status
    if metric_key == "cash_reserve_status":
        return "ok" if compact.cash_reserve_status != "unknown" else "unknown"
    return _portfolio_deviation_status(compact.max_deviation_pp)


def _portfolio_compact_module_status(compact: PortfolioDeviationCompact) -> str:
    if compact.stale_status in {"stale", "unknown"}:
        return compact.stale_status
    return _portfolio_deviation_status(compact.max_deviation_pp)


def _portfolio_deviation_status(value: float | None) -> str:
    if value is None:
        return "unknown"
    abs_value = abs(value)
    if abs_value < 3.0:
        return "ok"
    if abs_value <= 5.0:
        return "watch"
    return "pressure"


def _derived_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
) -> DashboardMetric | None:
    if metric_key == "credit_stress_status":
        if _find_metric("credit_stress_status", reports, include_aliases=False) is not None:
            return None
        return _credit_stress_status_metric(reports)
    if metric_key == "real_yield_pressure_status":
        if _find_metric("real_yield_pressure_status", reports, include_aliases=False) is not None:
            return None
        return _real_yield_pressure_status_metric(reports)
    if metric_key == "dgs30_distance_to_5pct":
        found = _find_metric("dgs30", reports)
        if found is None or _dependency_unusable(found):
            return _blocked_dependency_metric(
                metric_key="dgs30_distance_to_5pct",
                display_name="30Y distance to 5%",
                unit="pp",
                status="missing",
                missing_reason="DGS30 is missing; distance to 5% cannot be calculated.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Distance requires daily DGS30 compact evidence.",
            )
        dgs30_value = _to_float(found[0])
        if not isinstance(dgs30_value, float):
            return _blocked_dependency_metric(
                metric_key="dgs30_distance_to_5pct",
                display_name="30Y distance to 5%",
                unit="pp",
                status="missing",
                missing_reason="DGS30 is missing; distance to 5% cannot be calculated.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Distance requires numeric daily DGS30 compact evidence.",
            )
        value = round(dgs30_value - 5.0, 4)
        return _derived_metric_response(
            metric_key,
            "30Y distance to 5%",
            value,
            "pp",
            "pp",
            found,
            "Distance is derived from daily DGS30; it is not intraday.",
        )
    if metric_key == "dgs30_breakout_confirmed":
        found = _find_metric("dgs30_breakout_confirmed", reports)
        if found is None:
            return _blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="research_needed",
                missing_reason=DGS30_BREAKOUT_MISSING_REASON,
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Breakout confirmation requires explicit compact evidence; do not infer it.",
            )
        dgs30 = _find_metric("dgs30", reports)
        if dgs30 is None or _dependency_unusable(dgs30):
            return _blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="missing",
                missing_reason="DGS30 is missing; breakout confirmation cannot be evaluated.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Breakout confirmation requires DGS30 and explicit compact history evidence.",
            )
        _, payload, report = found
        if _dependency_unusable(found):
            return None
        if not _has_breakout_history_evidence(payload):
            return _blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="insufficient_history",
                missing_reason="DGS30 breakout confirmation requires compact history window evidence.",
                generated_at=_metric_generated_at(payload, report),
                interpretation_hint="Breakout confirmation requires explicit compact evidence; do not infer it.",
            )
    if metric_key == "nasdaq_vs_sp500_30d":
        nasdaq = _find_metric("nasdaq100_30d_return", reports)
        sp500 = _find_metric("sp500_30d_return", reports)
        if nasdaq is None or sp500 is None or _dependency_unusable(nasdaq) or _dependency_unusable(sp500):
            return _blocked_dependency_metric(
                metric_key="nasdaq_vs_sp500_30d",
                display_name="Nasdaq vs S&P 500 30D",
                unit="pp",
                status="insufficient_history",
                missing_reason="S&P 500 and Nasdaq 100 30D returns are both required.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Derived spread requires both compact 30D return metrics.",
            )
        nasdaq_value = _to_float(nasdaq[0])
        sp500_value = _to_float(sp500[0])
        if not isinstance(nasdaq_value, float) or not isinstance(sp500_value, float):
            return _blocked_dependency_metric(
                metric_key="nasdaq_vs_sp500_30d",
                display_name="Nasdaq vs S&P 500 30D",
                unit="pp",
                status="insufficient_history",
                missing_reason="S&P 500 and Nasdaq 100 30D returns must both be numeric.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Derived spread requires numeric compact 30D return metrics.",
            )
        value = round(nasdaq_value - sp500_value, 4)
        return _derived_metric_response(
            metric_key,
            "Nasdaq vs S&P 500 30D",
            value,
            "pp",
            "pp",
            nasdaq,
            "Derived spread between compact 30D return metrics.",
        )
    return None


def _credit_stress_status_metric(
    reports: tuple[ReportState, ...],
) -> DashboardMetric:
    high_yield = _usable_numeric_metric("high_yield_spread", reports)
    investment_grade = _usable_numeric_metric("investment_grade_spread", reports)
    vix = _usable_numeric_metric("vix", reports)
    generated_at = _latest_metric_timestamp(
        [item for item in (high_yield, investment_grade, vix) if item is not None]
    ) or _first_updated_at([report for report in reports if report.data is not None])
    observation_date = _latest_metric_observation_date(
        [item for item in (high_yield, investment_grade, vix) if item is not None]
    )
    hint = (
        "Derived from available credit spread evidence plus VIX. VIX alone is not "
        "sufficient to infer systemic credit stress or crisis."
    )

    if high_yield is None and investment_grade is None:
        return _blocked_dependency_metric(
            metric_key="credit_stress_status",
            display_name="Credit stress status",
            unit=None,
            status="unknown" if vix is not None else "missing",
            missing_reason=(
                "Credit spread evidence is missing; VIX alone is not sufficient "
                "to classify credit stress."
            ),
            generated_at=generated_at,
            interpretation_hint=hint,
        )

    high_yield_value = high_yield[0] if high_yield else None
    investment_grade_value = investment_grade[0] if investment_grade else None
    vix_value = vix[0] if vix else None
    status, value, missing_reason = _credit_status_from_values(
        high_yield=high_yield_value,
        investment_grade=investment_grade_value,
        vix=vix_value,
    )
    return DashboardMetric(
        metric_key="credit_stress_status",
        display_name="Credit stress status",
        value=value,
        value_text=_format_value(value, "text", status),
        unit=None,
        status=status,
        source="dashboard_compact",
        source_badge="derived",
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status="fresh" if observation_date or generated_at else "unknown",
        missing_reason=missing_reason,
        interpretation_hint=hint,
        ai_context_allowed=_ai_context_allowed(
            status=status,
            source="dashboard_compact",
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status="fresh" if observation_date or generated_at else "unknown",
            interpretation_hint=hint,
        ),
    )


def _credit_status_from_values(
    *,
    high_yield: float | None,
    investment_grade: float | None,
    vix: float | None,
) -> tuple[str, str, str | None]:
    credit_values = [value for value in (high_yield, investment_grade) if value is not None]
    if not credit_values:
        return "unknown", "spread_data_missing", "Credit spread evidence is missing."

    high_yield_stress = high_yield is not None and high_yield >= 8.0
    investment_grade_stress = investment_grade is not None and investment_grade >= 3.0
    high_yield_pressure = high_yield is not None and high_yield >= 5.0
    investment_grade_pressure = investment_grade is not None and investment_grade >= 2.0
    high_yield_watch = high_yield is not None and high_yield >= 3.5
    investment_grade_watch = investment_grade is not None and investment_grade >= 1.5
    vix_pressure = vix is not None and vix >= 30.0
    vix_watch = vix is not None and vix >= 25.0

    if high_yield_stress or investment_grade_stress:
        return "stress", "credit_spreads_stressed", None
    if high_yield_pressure or investment_grade_pressure or (
        vix_pressure and (high_yield_watch or investment_grade_watch)
    ):
        return "pressure", "credit_pressure", None
    if high_yield_watch or investment_grade_watch or vix_watch:
        return "watch", "credit_watch", None
    if investment_grade is None:
        return (
            "watch",
            "partial_coverage",
            "Investment-grade spread is missing; credit stress coverage is partial.",
        )
    return "ok", "credit_calm", None


def _real_yield_pressure_status_metric(
    reports: tuple[ReportState, ...],
) -> DashboardMetric:
    real_yield = _usable_numeric_metric("dfii10", reports)
    breakeven = _usable_numeric_metric("t10yie", reports)
    generated_at = _latest_metric_timestamp(
        [item for item in (real_yield, breakeven) if item is not None]
    ) or _first_updated_at([report for report in reports if report.data is not None])
    observation_date = _latest_metric_observation_date(
        [item for item in (real_yield, breakeven) if item is not None]
    )
    hint = (
        "Derived from 10Y real yield (DFII10) and 10Y breakeven inflation (T10YIE). "
        "Real yield pressure is a valuation and opportunity-cost mechanism, not a sole "
        "driver of equities, gold, or portfolio action."
    )
    if real_yield is None or breakeven is None:
        missing = []
        if real_yield is None:
            missing.append("DFII10")
        if breakeven is None:
            missing.append("T10YIE")
        return _blocked_dependency_metric(
            metric_key="real_yield_pressure_status",
            display_name="Real yield pressure status",
            unit=None,
            status="missing",
            missing_reason=(
                "Real yield pressure status requires both "
                f"{' and '.join(missing)} compact evidence."
            ),
            generated_at=generated_at,
            interpretation_hint=hint,
        )

    status, value = _real_yield_status_from_values(
        real_yield=real_yield[0],
        breakeven=breakeven[0],
    )
    freshness_status = "fresh" if observation_date or generated_at else "unknown"
    return DashboardMetric(
        metric_key="real_yield_pressure_status",
        display_name="Real yield pressure status",
        value=value,
        value_text=_format_value(value, "text", status),
        unit=None,
        status=status,
        source="dashboard_compact",
        source_badge="derived",
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=hint,
        ai_context_allowed=_ai_context_allowed(
            status=status,
            source="dashboard_compact",
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=hint,
        ),
    )


def _real_yield_status_from_values(
    *,
    real_yield: float,
    breakeven: float,
) -> tuple[str, str]:
    if real_yield >= 2.0:
        return "pressure", "real_yield_pressure"
    if real_yield >= 1.5 or breakeven >= 2.5:
        return "watch", "real_yield_watch"
    return "ok", "real_yield_calm"


def _derived_metric_response(
    metric_key: str,
    display_name: str,
    value: float,
    unit: str,
    format_kind: str,
    source_metric: tuple[Any, dict[str, Any], ReportState],
    interpretation_hint: str,
) -> DashboardMetric:
    _, payload, report = source_metric
    generated_at = _metric_generated_at(payload, report)
    observation_date = _metric_observation_date(payload)
    freshness_status = _metric_freshness(payload, report)
    source = _metric_source(payload, report)
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=_format_value(value, format_kind, "ok"),
        unit=unit,
        status="ok",
        source=source,
        source_badge="derived",
        source_series=_metric_source_series(payload, None, None),
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=_ai_context_allowed(
            status="ok",
            source=source,
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=interpretation_hint,
        ),
    )


def _blocked_dependency_metric(
    *,
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    missing_reason: str,
    generated_at: str | None,
    interpretation_hint: str | None,
) -> DashboardMetric:
    normalized_status = _metric_status_value(status)
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text=_missing_value_text(normalized_status),
        unit=unit,
        status=normalized_status,
        source=None,
        source_badge="research_needed" if normalized_status == "research_needed" else "missing",
        source_series=None,
        observation_date=None,
        generated_at=generated_at,
        freshness_status="missing"
        if normalized_status == "missing"
        else "unknown" if normalized_status == "unknown"
        else "insufficient_history",
        missing_reason=missing_reason,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=False,
    )


def _missing_metric(
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    generated_at: str | None,
    interpretation_hint: str | None = None,
    source: str | None = None,
    source_badge: str | None = None,
    missing_reason: str | None = None,
) -> DashboardMetric:
    normalized_status = _metric_status_value(status)
    normalized_source_badge = (
        source_badge
        if source_badge in ALLOWED_SOURCE_BADGES
        else "research_needed" if normalized_status == "research_needed" else "missing"
    )
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text=_missing_value_text(normalized_status),
        unit=unit,
        status=normalized_status,
        source=source,
        source_badge=normalized_source_badge,
        source_series=None,
        observation_date=None,
        generated_at=generated_at,
        freshness_status="unknown",
        missing_reason=missing_reason
        or (
            DGS30_BREAKOUT_MISSING_REASON
            if metric_key == "dgs30_breakout_confirmed"
            else _missing_value_text(normalized_status)
        ),
        interpretation_hint=interpretation_hint,
        ai_context_allowed=False,
    )


def _find_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
    *,
    include_aliases: bool = True,
) -> tuple[Any, dict[str, Any], ReportState] | None:
    metric_keys = (
        (metric_key, *METRIC_ALIASES.get(metric_key, ()), *official_macro_pack.aliases_for(metric_key))
        if include_aliases
        else (metric_key,)
    )
    for report in reports:
        if report.data is None:
            continue
        for key in metric_keys:
            found = _find_metric_payload(report.data, key)
            if found is None:
                continue
            if key != metric_key and _alias_payload_unusable(found):
                continue
            value, payload = found
            return value, payload, report
    return None


def _usable_numeric_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
) -> tuple[float, dict[str, Any], ReportState] | None:
    found = _find_metric(metric_key, reports)
    if found is None or _dependency_unusable(found):
        return None
    value = _to_float(found[0])
    if not isinstance(value, float):
        return None
    return value, found[1], found[2]


def _latest_metric_timestamp(
    found_items: list[tuple[float, dict[str, Any], ReportState]],
) -> str | None:
    candidates = [
        _metric_generated_at(payload, report)
        for _, payload, report in found_items
    ]
    return max([item for item in candidates if item], default=None)


def _latest_metric_observation_date(
    found_items: list[tuple[float, dict[str, Any], ReportState]],
) -> str | None:
    candidates = [
        _metric_observation_date(payload)
        for _, payload, _ in found_items
    ]
    return max([item for item in candidates if item], default=None)


def _alias_payload_unusable(found: tuple[Any, dict[str, Any]]) -> bool:
    value, payload = found
    if not isinstance(payload, dict):
        return value is None
    if "value" not in payload and "value_text" not in payload:
        return True
    return value is None


def _find_metric_payload(value: Any, metric_key: str) -> tuple[Any, dict[str, Any]] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() == metric_key.lower():
                if isinstance(child, dict):
                    child_value = _extract_metric_value(child)
                    return child_value, child
                return child, {"value": child}
        for child in value.values():
            found = _find_metric_payload(child, metric_key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_metric_payload(child, metric_key)
            if found is not None:
                return found
    return None


def _extract_metric_value(payload: dict[str, Any]) -> Any:
    if "value" in payload:
        return payload.get("value")
    for key in ("value", "value_text", "status", "label", "date", "updated_at"):
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _metric_status(payload: dict[str, Any]) -> str:
    return _metric_status_value(payload.get("status") or "ok")


def _metric_status_value(value: Any) -> str:
    status = str(value or "unknown").lower()
    return status if status in ALLOWED_METRIC_STATUSES else "unknown"


def _metric_freshness(
    payload: dict[str, Any],
    report: ReportState,
    metric_key: str | None = None,
    quality_metadata: dict[str, Any] | None = None,
) -> str:
    freshness = payload.get("freshness_status")
    if freshness is None and isinstance(payload.get("freshness"), dict):
        freshness = payload["freshness"].get("freshness_status")
    if freshness is None and isinstance(payload.get("freshness"), str):
        freshness = payload.get("freshness")
    if freshness is None and quality_metadata:
        freshness = quality_metadata.get("freshness_status") or quality_metadata.get("freshness")
    if freshness is None and metric_key:
        quality = _metric_quality_metadata(report, metric_key)
        freshness = quality.get("freshness_status") or quality.get("freshness")
    if freshness is None and metric_key == "holdings_updated_at" and isinstance(report.data, dict):
        freshness = report.data.get("holdings_freshness_status")
    if freshness is None and _contains_signal(payload, ("stale_cache",)):
        freshness = "stale"
    if freshness is None and report.data is not None and _contains_signal(report.data, ("stale_cache",)):
        freshness = "stale"
    return str(freshness or "unknown").lower()


def _metric_source(
    payload: dict[str, Any],
    report: ReportState,
    quality_metadata: dict[str, Any] | None = None,
) -> str | None:
    source = payload.get("source")
    if source is None and isinstance(payload.get("metadata"), dict):
        source = payload["metadata"].get("source")
    if source is None and quality_metadata:
        source = quality_metadata.get("source") or quality_metadata.get("provider")
    if source is None and isinstance(report.data, dict):
        source = report.data.get("source")
    if source is None and report.name == "portfolio_snapshot":
        source = "local"
    return _string_or_none(source)


def _metric_source_series(
    payload: dict[str, Any],
    quality_metadata: dict[str, Any] | None = None,
    official_macro: official_macro_pack.OfficialMacroMetric | None = None,
) -> str | None:
    source_series = payload.get("source_series")
    if source_series is None and isinstance(payload.get("metadata"), dict):
        source_series = payload["metadata"].get("source_series")
    if source_series is None and quality_metadata:
        source_series = quality_metadata.get("source_series")
    if source_series is None and official_macro:
        source_series = official_macro.source_series
    text = _string_or_none(source_series)
    if text and ":" in text:
        return text.split(":")[-1]
    return text


def _metric_source_badge(
    payload: dict[str, Any],
    report: ReportState,
    module_key: str,
    metric_key: str | None = None,
    quality_metadata: dict[str, Any] | None = None,
) -> str:
    if module_key == "portfolio_deviation":
        return "local"
    if metric_key in DERIVED_METRIC_KEYS and (
        payload.get("source_series") is not None
        or payload.get("derived_from") is not None
        or metric_key in {"dgs10_5d_avg", "dgs30_distance_to_5pct", "nasdaq_vs_sp500_30d"}
    ):
        return "derived"
    badge = payload.get("source_badge") or payload.get("source_tier")
    if badge is None and isinstance(payload.get("freshness"), dict):
        badge = payload["freshness"].get("source_tier")
    if badge is None and quality_metadata:
        badge = quality_metadata.get("source_badge") or quality_metadata.get("source_tier")
    if badge is None and isinstance(report.data, dict):
        badge = report.data.get("source_badge") or report.data.get("source_tier")
    badge_text = str(badge or "missing").lower()
    badge_text = SOURCE_BADGE_ALIASES.get(badge_text, badge_text)
    if badge_text in {"official", "official_fallback", "unofficial_fallback", "proxy", "search-derived"}:
        return badge_text
    return badge_text if badge_text in ALLOWED_SOURCE_BADGES else "missing"


def _metric_observation_date(
    payload: dict[str, Any],
    quality_metadata: dict[str, Any] | None = None,
) -> str | None:
    return _string_or_none(
        payload.get("observation_date")
        or payload.get("date")
        or payload.get("updated_at")
        or (quality_metadata or {}).get("observation_date")
    )


def _metric_generated_at(payload: dict[str, Any], report: ReportState) -> str | None:
    if payload.get("generated_at") is not None:
        return _string_or_none(payload.get("generated_at"))
    if isinstance(report.data, dict):
        return _string_or_none(report.data.get("generated_at") or report.data.get("updated_at"))
    return None


def _metric_quality_metadata(report: ReportState, metric_key: str) -> dict[str, Any]:
    if not isinstance(report.data, dict):
        return {}
    data_quality = report.data.get("data_quality")
    if isinstance(data_quality, dict):
        market_quality = data_quality.get("market_data_quality")
        if isinstance(market_quality, dict) and isinstance(market_quality.get(metric_key), dict):
            return market_quality[metric_key]
    if report.name == "portfolio_snapshot" and metric_key == "holdings_updated_at":
        return {
            "source": "local",
            "source_badge": "local",
            "observation_date": report.data.get("holdings_updated_at"),
            "freshness_status": report.data.get("holdings_freshness_status"),
        }
    return {}


def _first_metric_quality_metadata(
    reports: tuple[ReportState | None, ...],
    metric_key: str,
) -> dict[str, Any]:
    for report in reports:
        if report is None:
            continue
        metadata = _metric_quality_metadata(report, metric_key)
        if metadata:
            return metadata
    return {}


def _format_value(value: Any, format_kind: str, status: str) -> str:
    if status in {"missing", "research_needed", "insufficient_history", "not_available"}:
        return _missing_value_text(status)
    if status == "stale" and value is None:
        return "stale"
    if value is None:
        return "missing"
    if format_kind == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        return "unknown"
    if format_kind == "percent":
        number = _to_float(value)
        return f"{number:.2f}%" if isinstance(number, float) else str(value)
    if format_kind == "signed_percent":
        number = _to_float(value)
        return f"{number:+.2f}%" if isinstance(number, float) else str(value)
    if format_kind == "pp":
        number = _to_float(value)
        return f"{number:+.1f}pp" if isinstance(number, float) else str(value)
    if format_kind == "number":
        number = _to_float(value)
        if isinstance(number, float):
            return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"
        return str(value)
    return str(value)


def _normalize_inflation_yoy_value(
    metric_key: str,
    value: Any,
    payload: dict[str, Any],
) -> float | str | None:
    if metric_key not in INFLATION_YOY_METRIC_KEYS:
        return None
    number = _to_float(value)
    if number is None:
        return None
    if _payload_declares_index_level(payload) or abs(number) > 50.0:
        return "index_level"
    if -1.0 < number < 1.0 and number != 0.0:
        return round(number * 100.0, 6)
    return number


def _payload_declares_index_level(payload: dict[str, Any]) -> bool:
    for key in ("value_type", "metric_kind", "calculation", "unit"):
        text = str(payload.get(key) or "").lower()
        if "index" in text and "yoy" not in text and "year" not in text:
            return True
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return _payload_declares_index_level(metadata)
    return False


def _missing_value_text(status: str) -> str:
    if status == "research_needed":
        return "research needed"
    if status == "insufficient_history":
        return "insufficient history"
    if status == "stale":
        return "stale"
    if status == "not_available":
        return "not available"
    if status == "unknown":
        return "unknown"
    return "missing"


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace("%", ""))
        except ValueError:
            return None
    return None


def _interpretation_hint(metric_key: str) -> str | None:
    official_macro = official_macro_pack.get_official_macro_metric(metric_key)
    if official_macro is not None:
        return official_macro.interpretation_hint
    if metric_key in {"dgs10", "dgs10_5d_avg", "dgs30_distance_to_5pct"}:
        return "FRED Treasury yield series are daily, not intraday."
    if metric_key == "dgs30_breakout_confirmed":
        return "Breakout confirmation requires explicit compact evidence; do not infer it."
    if metric_key == "ppiaco_yoy":
        return "PPIACO is not final demand PPI."
    if metric_key in {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
    }:
        return PORTFOLIO_COMPACT_INTERPRETATION_HINT
    return None


def _ai_context_allowed(
    status: str,
    source: str | None,
    source_badge: str,
    observation_date: str | None,
    generated_at: str | None,
    freshness_status: str,
    interpretation_hint: str | None = None,
) -> bool:
    if _ai_context_blocked_reason(
        status=status,
        value=True,
        source=source,
        source_badge=source_badge,
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        interpretation_hint=interpretation_hint,
    ):
        return False
    return True


def _ai_context_blocked_reason(
    *,
    status: str,
    value: Any,
    source: str | None,
    source_badge: str,
    observation_date: str | None,
    generated_at: str | None,
    freshness_status: str,
    interpretation_hint: str | None = None,
) -> str | None:
    if value is None:
        return "value_missing"
    if status in AI_BLOCKED_METRIC_STATUSES:
        return f"status_{status}"
    if source_badge in AI_BLOCKED_SOURCE_BADGES:
        return f"source_badge_{source_badge}"
    has_date = bool(observation_date or generated_at)
    if freshness_status in AI_BLOCKED_FRESHNESS_STATUSES:
        if not (source_badge == "local" and bool(generated_at)):
            return f"freshness_{freshness_status}"
    if source_badge == "proxy":
        return "source_badge_proxy"
    if source_badge == "derived" and not _derived_dependency_hint_complete(interpretation_hint):
        return "dependency_metadata_incomplete"
    if not source and source_badge not in {"local", "derived"}:
        return "source_missing"
    if not has_date:
        return "date_missing"
    return None


def _metric_interpretation_hint(metric_key: str, payload: dict[str, Any]) -> str | None:
    hint = _string_or_none(payload.get("interpretation_hint"))
    if metric_key == "ppiaco_yoy" and hint:
        if "final demand" not in hint.lower():
            return f"{hint} PPIACO is not final demand PPI."
        return hint
    if metric_key in {"ppi_final_demand", "ppi_final_demand_yoy"} and hint:
        text = hint.lower()
        if "ppiaco" not in text or "consensus" not in text:
            return (
                f"{hint} PPI Final Demand is distinct from PPIACO and must not be "
                "described as above or below consensus without consensus data."
            )
        return hint
    return hint or _interpretation_hint(metric_key)


def _derived_dependency_hint_complete(interpretation_hint: str | None) -> bool:
    text = (interpretation_hint or "").lower()
    return any(
        marker in text
        for marker in (
            "derived",
            "average",
            "history",
            "historical",
            "observation",
            "observations",
            "window",
            "compact",
        )
    )


def _dependency_unusable(found: tuple[Any, dict[str, Any], ReportState]) -> bool:
    value, payload, report = found
    status = _metric_status(payload)
    freshness = _metric_freshness(payload, report)
    if status in AI_BLOCKED_METRIC_STATUSES:
        return True
    if freshness in {"missing", "insufficient_history", "stale"}:
        return True
    return value is None


def _has_breakout_history_evidence(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "window_observation_count",
            "above_5pct_days_5d",
            "five_observation_average",
            "calculation",
        )
    )


def _module_status_with_coverage(
    module_key: str,
    status: str,
    key_metrics: list[DashboardMetric],
) -> tuple[str, str | None]:
    if status in {"error", "missing", "stale"}:
        return status, None
    core_metrics = [
        metric
        for metric in key_metrics
        if metric.metric_key in CORE_METRIC_KEYS.get(module_key, set())
    ]
    if not core_metrics:
        return status, None

    blocked = [
        metric for metric in core_metrics if metric.status in AI_BLOCKED_METRIC_STATUSES
    ]
    stale = [metric for metric in core_metrics if metric.freshness_status == "stale"]
    if len(blocked) == len(core_metrics):
        return "unknown", "core metric coverage unavailable"
    if stale:
        return "stale", "one or more core metrics are stale"
    if blocked and status == "ok":
        return "unknown", "partial core metric coverage"
    return status, None


def _summary_with_coverage_note(summary: str | None, coverage_note: str | None) -> str | None:
    if not coverage_note:
        return summary
    if not summary:
        return coverage_note
    if coverage_note in summary:
        return summary
    return f"{summary}; {coverage_note}"


def _missing_data(reports: dict[str, ReportState]) -> list[dict]:
    missing = []
    for name, report in reports.items():
        if not report.exists:
            missing.append(
                {
                    "key": name,
                    "status": "missing",
                    "summary": f"{report.path.name} missing",
                    "next_action": _next_action_for_report(name),
                }
            )
        elif report.error_summary is not None:
            missing.append(
                {
                    "key": name,
                    "status": "error",
                    "summary": report.error_summary,
                    "next_action": _next_action_for_report(name),
                }
            )
        else:
            compact_missing = _compact_missing_entries(report.data)
            for entry in compact_missing:
                missing.append({"key": name, **entry})
    return missing


def _compact_missing_entries(data: dict[str, Any] | None) -> list[dict]:
    if not isinstance(data, dict):
        return []
    entries = []
    for field in (
        "missing_required_inputs",
        "missing_optional_inputs",
        "research_needed",
        "not_available",
    ):
        value = data.get(field)
        if isinstance(value, list):
            entries.append(
                {
                    "status": "missing",
                    "summary": f"{field}: {len(value)} item(s)",
                }
            )
    return entries


def _data_freshness(reports: dict[str, ReportState], provider_health: dict) -> dict:
    files = {}
    for name, report in reports.items():
        files[name] = {
            "status": _report_status(report),
            "generated_at": _string_or_none(
                report.data.get("generated_at")
                if isinstance(report.data, dict)
                else None
            ),
            "stale_cache": _contains_signal(report.data, ("stale_cache",)),
            "next_action": _next_action_for_report(name)
            if _report_status(report) in {"missing", "error", "stale"}
            else None,
        }
    return {
        "status": _freshness_status(files),
        "files": files,
        "provider_health_generated_at": provider_health.get("generated_at"),
    }


def _next_actions(modules: dict[str, DashboardModule], provider_health: dict) -> list[str]:
    actions = []
    for module in modules.values():
        if module.next_action:
            actions.append(module.next_action)
    provider_action = provider_health.get("next_action")
    if provider_action:
        actions.append(str(provider_action))
    return sorted(set(actions))


def _overall_status(modules: dict[str, DashboardModule], provider_health: dict) -> str:
    statuses = {module.status for module in modules.values()}
    provider_status = provider_health.get("overall_status")
    if "error" in statuses or provider_status == "error":
        return "error"
    if statuses == {"missing"} and provider_status == "not_run_yet":
        return "missing"
    if statuses & {"missing", "stale", "degraded", "unknown", "watch", "pressure", "stress"} or provider_status in {
        "degraded",
        "transient_error",
        "not_run_yet",
    }:
        return "degraded"
    if statuses == {"ok"} and provider_status in {"ok", None}:
        return "ok"
    return "unknown"


def _overall_risk_level(reports: dict[str, ReportState]) -> str | None:
    for report in (reports["market_temperature"], reports["market_snapshot"]):
        if report.data is None:
            continue
        for key in ("overall_risk_level", "risk_level", "temperature_label"):
            value = _string_or_none(report.data.get(key))
            if value:
                return value
    return None


def _first_generated_at(reports: dict[str, ReportState], provider_health: dict) -> str | None:
    for report in (
        reports["market_temperature"],
        reports["market_snapshot"],
        reports["portfolio_snapshot"],
    ):
        if report.data is None:
            continue
        value = _string_or_none(report.data.get("generated_at"))
        if value:
            return value
    return _string_or_none(provider_health.get("generated_at"))


def _first_error(reports: tuple[ReportState, ...]) -> str | None:
    for report in reports:
        if report.error_summary is not None:
            return report.error_summary
    return None


def _first_status(reports: list[ReportState]) -> str | None:
    for report in reports:
        value = _string_or_none(report.data.get("status") if report.data else None)
        if value:
            return value
    return None


def _first_updated_at(reports: list[ReportState]) -> str | None:
    for report in reports:
        if report.data is None:
            continue
        value = _string_or_none(
            report.data.get("generated_at") or report.data.get("updated_at")
        )
        if value:
            return value
    return None


def _contains_signal(value: Any, signal_terms: tuple[str, ...]) -> bool:
    terms = tuple(term.lower() for term in signal_terms)
    return _contains_signal_key(value, terms)


def _contains_signal_key(value: Any, signal_terms: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if any(term in key_text for term in signal_terms):
                return True
            if _contains_signal_key(child, signal_terms):
                return True
    elif isinstance(value, list):
        return any(_contains_signal_key(item, signal_terms) for item in value)
    elif isinstance(value, str):
        text = value.lower()
        return any(text == term for term in signal_terms)
    return False


def _report_status(report: ReportState) -> str:
    if not report.exists:
        return "missing"
    if report.error_summary is not None:
        return "error"
    if report.data is None:
        return "unknown"
    if _contains_signal(report.data, ("stale_cache",)):
        return "stale"
    return _coerce_status(report.data.get("status"), default="ok")


def _freshness_status(files: dict[str, dict]) -> str:
    statuses = {item["status"] for item in files.values()}
    if "error" in statuses:
        return "error"
    if "stale" in statuses:
        return "stale"
    if "missing" in statuses:
        return "degraded"
    if statuses == {"ok"}:
        return "ok"
    return "unknown"


def _next_action_for_report(name: str) -> str:
    if name == "provider_health":
        return provider_service.NEXT_ACTION
    if name == "portfolio_snapshot":
        return "python scripts/run_portfolio_check.py"
    return _run_reports_action()


def _run_reports_action() -> str:
    return "python scripts/run_market_data_check.py"


def _coerce_status(value: Any, default: str = "unknown") -> str:
    allowed = {
        "ok",
        "watch",
        "pressure",
        "stress",
        "missing",
        "stale",
        "degraded",
        "error",
        "not_run_yet",
        "unknown",
    }
    status = str(value or default).lower()
    return status if status in allowed else default


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _safe_error_summary(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[redacted]", text)
    text = re.sub(
        r"(?i)(api[_-]?key|apikey|token|secret)=([^&\s]+)",
        r"\1=[redacted]",
        text,
    )
    if len(text) > MAX_ERROR_SUMMARY_LENGTH:
        return text[:MAX_ERROR_SUMMARY_LENGTH].rstrip()
    return text


def _model_to_dict(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()
