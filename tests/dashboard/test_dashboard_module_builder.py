from pathlib import Path

from app_backend.schemas.responses import DashboardMetric
from app_backend.services import dashboard_module_builder
from app_backend.services.dashboard_composition import compose_dashboard_builders
from app_backend.services.dashboard_evidence_policy import AI_BLOCKED_METRIC_STATUSES
from app_backend.services.dashboard_metric_catalog import CORE_METRIC_KEYS
from app_backend.services.dashboard_report_loader import ReportState


MODULE_KEYS = {
    "credit_stress",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy_pressure",
    "equity_trend",
    "breadth_concentration_proxy",
    "market_stress_derived",
    "portfolio_deviation",
}


def test_build_modules_preserves_module_keys(tmp_path):
    reports = {
        "market_snapshot": _report("market_snapshot", tmp_path, exists=False),
        "market_temperature": _report("market_temperature", tmp_path, exists=False),
        "portfolio_snapshot": _report("portfolio_snapshot", tmp_path, exists=False),
        "provider_health": _report("provider_health", tmp_path, exists=False),
    }

    modules = compose_dashboard_builders().build_modules(reports)

    assert set(modules) == MODULE_KEYS


def test_module_status_with_coverage_characterization():
    core = {"example": {"core_a", "core_b"}}
    blocked_statuses = {"missing", "research_needed", "insufficient_history"}

    all_blocked = [
        _metric("core_a", status="missing"),
        _metric("core_b", status="research_needed"),
    ]
    assert dashboard_module_builder.module_status_with_coverage(
        "example",
        "ok",
        all_blocked,
        core_metric_keys=core,
        ai_blocked_metric_statuses=blocked_statuses,
    ) == ("unknown", "core metric coverage unavailable")

    stale_core = [
        _metric("core_a", freshness_status="stale"),
        _metric("core_b"),
    ]
    assert dashboard_module_builder.module_status_with_coverage(
        "example",
        "ok",
        stale_core,
        core_metric_keys=core,
        ai_blocked_metric_statuses=blocked_statuses,
    ) == ("stale", "one or more core metrics are stale")

    partial_blocked = [
        _metric("core_a", status="missing"),
        _metric("core_b"),
    ]
    assert dashboard_module_builder.module_status_with_coverage(
        "example",
        "ok",
        partial_blocked,
        core_metric_keys=core,
        ai_blocked_metric_statuses=blocked_statuses,
    ) == ("unknown", "partial core metric coverage")

    assert dashboard_module_builder.module_status_with_coverage(
        "other",
        "ok",
        partial_blocked,
        core_metric_keys=core,
        ai_blocked_metric_statuses=blocked_statuses,
    ) == ("ok", None)


def test_summary_with_coverage_note_characterization():
    note = "partial core metric coverage"

    assert dashboard_module_builder.summary_with_coverage_note(None, note) == note
    assert dashboard_module_builder.summary_with_coverage_note("summary", None) == "summary"
    assert (
        dashboard_module_builder.summary_with_coverage_note(
            f"summary; {note}",
            note,
        )
        == f"summary; {note}"
    )
    assert (
        dashboard_module_builder.summary_with_coverage_note("summary", note)
        == f"summary; {note}"
    )


def test_portfolio_module_missing_report_characterization(tmp_path):
    report = _report("portfolio_snapshot", tmp_path, exists=False)

    module = dashboard_module_builder.portfolio_module(
        report,
        key_metrics_for_module=_empty_key_metrics,
        portfolio_deviation_compact=lambda report: None,
        portfolio_compact_module_status=lambda compact: "ok",
        core_metric_keys=CORE_METRIC_KEYS,
        ai_blocked_metric_statuses=AI_BLOCKED_METRIC_STATUSES,
    )

    assert module.status == "missing"
    assert module.source_badge == "missing_report"
    assert module.next_action == "python scripts/run_portfolio_check.py"


def test_portfolio_module_error_report_characterization(tmp_path):
    report = ReportState(
        name="portfolio_snapshot",
        path=tmp_path / "portfolio_snapshot.json",
        exists=True,
        error_summary="api_key=secret-value sk-abcdefghijklmnopqrstuvwxyz",
    )

    module = dashboard_module_builder.portfolio_module(
        report,
        key_metrics_for_module=_empty_key_metrics,
        portfolio_deviation_compact=lambda report: None,
        portfolio_compact_module_status=lambda compact: "ok",
        core_metric_keys=CORE_METRIC_KEYS,
        ai_blocked_metric_statuses=AI_BLOCKED_METRIC_STATUSES,
    )

    assert module.status == "error"
    assert module.source_badge == "report_error"
    assert module.error_summary is not None
    assert "secret-value" not in module.error_summary
    assert "abcdefghijklmnopqrstuvwxyz" not in module.error_summary


def test_dashboard_module_builder_has_no_reverse_import():
    source = Path(dashboard_module_builder.__file__).read_text(encoding="utf-8")

    assert "dashboard_service" not in source


def _empty_key_metrics(*args, **kwargs):
    return []


def _report(name, tmp_path, *, exists=True, data=None, error_summary=None):
    return ReportState(
        name=name,
        path=tmp_path / f"{name}.json",
        exists=exists,
        data=data,
        error_summary=error_summary,
    )


def _metric(
    metric_key,
    *,
    status="ok",
    freshness_status="fresh",
    value=1.0,
):
    return DashboardMetric(
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value),
        unit=None,
        status=status,
        source=None,
        source_badge="official",
        observation_date=None,
        generated_at=None,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=None,
        ai_context_allowed=status == "ok",
    )
