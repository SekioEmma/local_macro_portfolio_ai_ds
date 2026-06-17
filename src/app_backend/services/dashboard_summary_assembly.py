"""Summary response assembly and shared text/status helpers.

Pure extraction from dashboard_service: provider health summary, missing data
detection, freshness aggregation, status coercion, and small text/path
utilities used across the dashboard service. The functions here are
behavior-preserving copies; dashboard_service re-exports them under their
original underscore-prefixed names so module/metric builders that still
live in dashboard_service can continue to use them without import changes
on the test surface.
"""

from __future__ import annotations

import re
from typing import Any

from app_backend.schemas.responses import DashboardModule
from app_backend.services import provider_service
from app_backend.services.dashboard_report_loader import ReportState


MAX_ERROR_SUMMARY_LENGTH = 200


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def coerce_status(value: Any, default: str = "unknown") -> str:
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


def safe_error_summary(value: Any) -> str | None:
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


def model_to_dict(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def contains_signal(value: Any, signal_terms: tuple[str, ...]) -> bool:
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


def first_error(reports: tuple[ReportState, ...]) -> str | None:
    for report in reports:
        if report.error_summary is not None:
            return report.error_summary
    return None


def first_status(reports: list[ReportState]) -> str | None:
    for report in reports:
        value = string_or_none(report.data.get("status") if report.data else None)
        if value:
            return value
    return None


def first_updated_at(reports: list[ReportState]) -> str | None:
    for report in reports:
        if report.data is None:
            continue
        value = string_or_none(
            report.data.get("generated_at") or report.data.get("updated_at")
        )
        if value:
            return value
    return None


def first_generated_at(reports: dict[str, ReportState], provider_health: dict) -> str | None:
    for report in (
        reports["market_temperature"],
        reports["market_snapshot"],
        reports["portfolio_snapshot"],
    ):
        if report.data is None:
            continue
        value = string_or_none(report.data.get("generated_at"))
        if value:
            return value
    return string_or_none(provider_health.get("generated_at"))


def run_reports_action() -> str:
    return "python scripts/run_market_data_check.py"


def next_action_for_report(name: str) -> str:
    if name == "provider_health":
        return provider_service.NEXT_ACTION
    if name == "portfolio_snapshot":
        return "python scripts/run_portfolio_check.py"
    return run_reports_action()


def report_status(report: ReportState) -> str:
    if not report.exists:
        return "missing"
    if report.error_summary is not None:
        return "error"
    if report.data is None:
        return "unknown"
    if contains_signal(report.data, ("stale_cache",)):
        return "stale"
    return coerce_status(report.data.get("status"), default="ok")


def freshness_status(files: dict[str, dict]) -> str:
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


def compact_missing_entries(data: dict[str, Any] | None) -> list[dict]:
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


def missing_data(reports: dict[str, ReportState]) -> list[dict]:
    missing = []
    for name, report in reports.items():
        if not report.exists:
            missing.append(
                {
                    "key": name,
                    "status": "missing",
                    "summary": f"{report.path.name} missing",
                    "next_action": next_action_for_report(name),
                }
            )
        elif report.error_summary is not None:
            missing.append(
                {
                    "key": name,
                    "status": "error",
                    "summary": report.error_summary,
                    "next_action": next_action_for_report(name),
                }
            )
        else:
            compact_missing = compact_missing_entries(report.data)
            for entry in compact_missing:
                missing.append({"key": name, **entry})
    return missing


def data_freshness(reports: dict[str, ReportState], provider_health: dict) -> dict:
    files = {}
    for name, report in reports.items():
        files[name] = {
            "status": report_status(report),
            "generated_at": string_or_none(
                report.data.get("generated_at")
                if isinstance(report.data, dict)
                else None
            ),
            "stale_cache": contains_signal(report.data, ("stale_cache",)),
            "next_action": next_action_for_report(name)
            if report_status(report) in {"missing", "error", "stale"}
            else None,
        }
    return {
        "status": freshness_status(files),
        "files": files,
        "provider_health_generated_at": provider_health.get("generated_at"),
    }


def next_actions(modules: dict[str, DashboardModule], provider_health: dict) -> list[str]:
    actions = []
    for module in modules.values():
        if module.next_action:
            actions.append(module.next_action)
    provider_action = provider_health.get("next_action")
    if provider_action:
        actions.append(str(provider_action))
    return sorted(set(actions))


def overall_status(modules: dict[str, DashboardModule], provider_health: dict) -> str:
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


def overall_risk_level(reports: dict[str, ReportState]) -> str | None:
    for report in (reports["market_temperature"], reports["market_snapshot"]):
        if report.data is None:
            continue
        for key in ("overall_risk_level", "risk_level", "temperature_label"):
            value = string_or_none(report.data.get(key))
            if value:
                return value
    return None


def provider_health_summary(health_path) -> dict:
    response = provider_service.build_provider_health(health_path)
    payload = model_to_dict(response)
    return {
        "generated_at": payload.get("generated_at"),
        "overall_status": payload.get("overall_status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "checks": payload.get("checks") if isinstance(payload.get("checks"), list) else [],
        "next_action": payload.get("next_action"),
        "error_summary": payload.get("error_summary"),
    }
