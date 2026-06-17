from types import SimpleNamespace

from app_backend.schemas.responses import DashboardEvidenceRow
from app_backend.services import ai_context_service, dashboard_service


def test_stage8_private_or_insufficient_rows_are_excluded_from_manifest(monkeypatch):
    rows = [
        _row(
            "portfolio_exposure_overlay_status",
            "available",
            status="ok",
            ai_context_allowed=True,
        ),
        _row(
            "portfolio_exposure_missing_inputs",
            "sanitized_portfolio_context",
            status="insufficient_evidence",
            ai_context_allowed=False,
            missing_reason="private_inputs_excluded_or_insufficient_context",
        ),
    ]
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
    )

    manifest = ai_context_service.build_ai_context_manifest()

    included_keys = {row["metric_key"] for row in manifest.included_model_outputs}
    excluded = {row["metric_key"]: row for row in manifest.excluded_model_outputs}
    assert "portfolio_exposure_overlay_status" in included_keys
    assert "portfolio_exposure_missing_inputs" in excluded
    assert excluded["portfolio_exposure_missing_inputs"]["excluded_reason"] == (
        "status_insufficient_evidence"
    )


def test_stage8_boundaries_are_manifest_constraints_not_d15_support(monkeypatch):
    rows = [
        _row(
            "portfolio_exposure_overlay_status",
            "available",
            status="ok",
            ai_context_allowed=True,
        ),
        _row(
            "macro_regime_label",
            "mixed_or_transition",
            module="macro_regime_review",
            status="ok",
            ai_context_allowed=True,
            input_evidence=[],
        ),
        _row(
            "scenario_stress_severity_band",
            "mild",
            module="scenario_stress",
            status="limited_evidence",
            ai_context_allowed=False,
        ),
        _row(
            "historical_validation_available_event_count",
            0,
            module="historical_validation",
            status="ok",
            ai_context_allowed=True,
        ),
    ]
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
    )

    manifest = ai_context_service.build_ai_context_manifest()
    macro = _included(manifest, "macro_regime_label")
    scenario_excluded = _excluded(manifest, "scenario_stress_severity_band")
    historical = _included(manifest, "historical_validation_available_event_count")

    assert any("Portfolio exposure overlay uses sanitized compact context only" in item for item in manifest.risk_boundaries)
    assert macro["input_evidence"] == []
    assert scenario_excluded["excluded_reason"] == "status_limited_evidence"
    assert historical["value"] == 0


def _included(manifest, metric_key):
    for row in manifest.included_model_outputs:
        if row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing included model output {metric_key}")


def _excluded(manifest, metric_key):
    for row in manifest.excluded_model_outputs:
        if row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing excluded model output {metric_key}")


def _row(
    metric_key,
    value,
    *,
    module="portfolio_exposure_overlay",
    status="ok",
    ai_context_allowed=True,
    missing_reason=None,
    input_evidence=None,
):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value),
        unit=None,
        status=status,
        source="local_rules",
        source_badge="derived",
        source_series="STAGE8_PORTFOLIO_EXPOSURE_OVERLAY_V0",
        observation_date="2026-06-01",
        generated_at="2026-06-01T00:00:00+00:00",
        freshness_status="historical",
        missing_reason=missing_reason,
        interpretation_hint=None,
        interpretation_boundary=(
            "Portfolio exposure overlay uses sanitized compact context only and "
            "is not an action directive or position-level output."
        ),
        ai_context_allowed=ai_context_allowed,
        blocked_reason=None if ai_context_allowed else f"status_{status}",
        input_evidence=input_evidence,
        component_contributions={
            "hard_gates": {
                "portfolio_overlay_cannot_create_d15_support": True,
                "portfolio_overlay_cannot_change_scenario_severity": True,
                "portfolio_overlay_cannot_create_d19_availability": True,
            }
        },
        trigger_eligibility="overlay_only",
    )
