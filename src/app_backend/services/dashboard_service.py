from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import DashboardModule, DashboardSummaryResponse
from app_backend.services import provider_service


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
MAX_ERROR_SUMMARY_LENGTH = 200
DASHBOARD_MODULE_KEYS = (
    "credit_stress",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy_pressure",
    "equity_trend",
    "portfolio_deviation",
)
REPORT_FILES = {
    "market_snapshot": "market_snapshot.json",
    "market_temperature": "market_temperature.json",
    "portfolio_snapshot": "portfolio_snapshot.json",
    "provider_health": "provider_health_check.json",
}


@dataclass(frozen=True)
class ReportState:
    name: str
    path: Path
    exists: bool
    data: dict[str, Any] | None = None
    error_summary: str | None = None


def build_dashboard_summary(reports_dir: Path | str | None = None) -> DashboardSummaryResponse:
    base_dir = Path(reports_dir) if reports_dir is not None else DEFAULT_REPORTS_DIR
    reports = {
        key: _load_report(key, base_dir / file_name)
        for key, file_name in REPORT_FILES.items()
    }
    provider_health = _provider_health_summary(
        base_dir / REPORT_FILES["provider_health"]
    )
    modules = _build_modules(reports)
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


def _load_report(name: str, path: Path) -> ReportState:
    if not path.exists():
        return ReportState(name=name, path=path, exists=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
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


def _provider_health_summary(health_path: Path) -> dict:
    response = provider_service.build_provider_health(health_path)
    payload = _model_to_dict(response)
    return {
        "generated_at": payload.get("generated_at"),
        "overall_status": payload.get("overall_status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "next_action": payload.get("next_action"),
        "error_summary": payload.get("error_summary"),
    }


def _build_modules(reports: dict[str, ReportState]) -> dict[str, DashboardModule]:
    market = reports["market_snapshot"]
    temperature = reports["market_temperature"]
    portfolio = reports["portfolio_snapshot"]
    return {
        "credit_stress": _market_module(
            key="credit_stress",
            label="credit stress",
            reports=(market, temperature),
            signal_terms=("financial_conditions", "high_yield_spread", "credit", "vix"),
        ),
        "rate_pressure": _market_module(
            key="rate_pressure",
            label="rate pressure",
            reports=(market,),
            signal_terms=("dgs10", "dgs30", "treasury_yields", "10y", "30y"),
        ),
        "real_yield_pressure": _market_module(
            key="real_yield_pressure",
            label="real yield pressure",
            reports=(market,),
            signal_terms=("real_yield_10y", "dfii10", "real_yield"),
        ),
        "inflation_energy_pressure": _market_module(
            key="inflation_energy_pressure",
            label="inflation and energy pressure",
            reports=(market, temperature),
            signal_terms=("cpi", "pce", "ppi", "oil", "energy", "inflation"),
        ),
        "equity_trend": _market_module(
            key="equity_trend",
            label="equity trend",
            reports=(market, temperature),
            signal_terms=("sp500", "nasdaq", "nasdaq100", "equity_temperature", "equity"),
        ),
        "portfolio_deviation": _portfolio_module(portfolio),
    }


def _market_module(
    key: str,
    label: str,
    reports: tuple[ReportState, ...],
    signal_terms: tuple[str, ...],
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
        )

    available_reports = [report for report in reports if report.data is not None]
    if not available_reports:
        return _module(
            key=key,
            status="missing",
            label=label,
            summary=f"{label} data missing",
            source_badge="missing_report",
            next_action=_run_reports_action(),
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
        )

    return _module(
        key=key,
        status="missing",
        label=label,
        summary=f"{label} compact signal missing",
        source_badge="cached_report",
        updated_at=_first_updated_at(available_reports),
        next_action=_run_reports_action(),
    )


def _portfolio_module(report: ReportState) -> DashboardModule:
    if report.error_summary is not None:
        return _module(
            key="portfolio_deviation",
            status="error",
            label="portfolio deviation",
            summary="portfolio snapshot invalid",
            source_badge="report_error",
            error_summary=report.error_summary,
        )
    if report.data is None:
        return _module(
            key="portfolio_deviation",
            status="missing",
            label="missing",
            summary="portfolio snapshot missing",
            source_badge="missing_report",
            next_action="python scripts/run_portfolio_check.py",
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
) -> DashboardModule:
    return DashboardModule(
        key=key,
        status=_coerce_status(status),
        label=label,
        summary=summary,
        source_badge=source_badge,
        updated_at=updated_at,
        next_action=next_action,
        error_summary=_safe_error_summary(error_summary),
    )


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
    if statuses & {"missing", "stale", "degraded"} or provider_status in {
        "degraded",
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
    allowed = {"ok", "missing", "stale", "degraded", "error", "not_run_yet", "unknown"}
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
