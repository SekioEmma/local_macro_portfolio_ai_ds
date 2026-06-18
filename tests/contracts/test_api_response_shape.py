"""API response shape contract tests.

Locks the exact field set of every response model the frontend consumes.
This is the "API freeze" for the frontend redesign phase: any field rename,
removal, or accidental addition must update this test deliberately, which
makes drift between backend and frontend visible at PR-review time.

The check uses pydantic's model_fields rather than parsing JSON output, so
it does not require a live request and does not depend on report fixtures.

If a test fails:
- A new field was added without an explicit decision -> update the expected
  set and check the frontend renders the field, or revert.
- An existing field was removed/renamed -> confirm the frontend is updated,
  then change the expected set in lockstep.
"""

from __future__ import annotations

from pydantic import BaseModel

from app_backend.schemas.responses import (
    AIContextManifestResponse,
    AppSettingsResponse,
    DashboardEvidenceRow,
    DashboardEvidenceTableResponse,
    DashboardMetric,
    DashboardModule,
    DashboardSummaryResponse,
    FavoriteAnswer,
    ProviderHealthCheck,
    ProviderHealthResponse,
    RefreshRun,
    StatusResponse,
    StorageStatusResponse,
)


def _fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields.keys())


def test_status_response_fields_locked():
    assert _fields(StatusResponse) == {
        "app_name",
        "mode",
        "storage_mode",
        "api_keys_configured",
        "privacy_boundaries",
        "project_root_exists",
    }


def test_provider_health_check_fields_locked():
    assert _fields(ProviderHealthCheck) == {
        "key",
        "provider",
        "status",
        "source",
        "observation_date",
        "value_present",
        "error_type",
        "error_summary",
    }


def test_provider_health_response_fields_locked():
    assert _fields(ProviderHealthResponse) == {
        "generated_at",
        "overall_status",
        "summary",
        "checks",
        "next_action",
        "error_summary",
    }


def test_dashboard_metric_fields_locked():
    assert _fields(DashboardMetric) == {
        "metric_key",
        "display_name",
        "value",
        "value_text",
        "unit",
        "status",
        "source",
        "source_badge",
        "source_series",
        "observation_date",
        "generated_at",
        "freshness_status",
        "missing_reason",
        "interpretation_hint",
        "ai_context_allowed",
        "input_evidence",
        "component_contributions",
        "missing_inputs",
        "interpretation_boundary",
        "lookback_window",
        "lookback_start",
        "lookback_end",
        "observation_count",
        "minimum_observation_count",
        "history_quality_status",
        "percentile",
        "percentile_band",
        "zscore",
        "zscore_band",
        "robust_zscore",
        "robust_zscore_band",
        "percentile_direction",
        "frequency_class",
        "transform_class",
        "ai_context_tier",
        "trigger_eligibility",
    }


def test_dashboard_module_fields_locked():
    assert _fields(DashboardModule) == {
        "key",
        "status",
        "label",
        "summary",
        "source_badge",
        "updated_at",
        "next_action",
        "error_summary",
        "key_metrics",
    }


def test_dashboard_summary_response_fields_locked():
    assert _fields(DashboardSummaryResponse) == {
        "generated_at",
        "overall_status",
        "overall_risk_level",
        "modules",
        "provider_health",
        "missing_data",
        "data_freshness",
        "next_actions",
    }


def test_dashboard_evidence_row_fields_locked():
    assert _fields(DashboardEvidenceRow) == {
        "row_id",
        "module",
        "metric_key",
        "display_name",
        "value",
        "value_text",
        "unit",
        "status",
        "source",
        "source_badge",
        "source_series",
        "observation_date",
        "generated_at",
        "freshness_status",
        "missing_reason",
        "interpretation_hint",
        "blocked_reason",
        "ai_context_allowed",
        "input_evidence",
        "component_contributions",
        "missing_inputs",
        "interpretation_boundary",
        "lookback_window",
        "lookback_start",
        "lookback_end",
        "observation_count",
        "minimum_observation_count",
        "history_quality_status",
        "percentile",
        "percentile_band",
        "zscore",
        "zscore_band",
        "robust_zscore",
        "robust_zscore_band",
        "percentile_direction",
        "frequency_class",
        "transform_class",
        "ai_context_tier",
        "trigger_eligibility",
    }


def test_dashboard_evidence_table_response_fields_locked():
    assert _fields(DashboardEvidenceTableResponse) == {
        "generated_at",
        "overall_status",
        "row_count",
        "modules",
        "rows",
        "filters",
        "next_actions",
    }


def test_ai_context_manifest_response_fields_locked():
    assert _fields(AIContextManifestResponse) == {
        "generated_at",
        "included_facts",
        "excluded_facts",
        "included_model_outputs",
        "excluded_model_outputs",
        "portfolio_context_policy",
        "privacy_policy",
        "search_policy",
        "model_destination",
        "persistence_policy",
        "risk_boundaries",
        "source_summary",
    }


def test_storage_status_response_fields_locked():
    assert _fields(StorageStatusResponse) == {
        "storage_mode",
        "database_exists",
        "schema_version",
        "initialized",
        "error_summary",
    }


def test_app_settings_response_fields_locked():
    assert _fields(AppSettingsResponse) == {
        "settings",
        "updated_at",
    }


def test_refresh_run_fields_locked():
    assert _fields(RefreshRun) == {
        "id",
        "kind",
        "status",
        "started_at",
        "finished_at",
        "summary",
        "error_summary",
        "created_at",
    }


def test_favorite_answer_fields_locked():
    assert _fields(FavoriteAnswer) == {
        "id",
        "title",
        "question",
        "answer",
        "model",
        "context_snapshot",
        "created_at",
    }


def test_dashboard_module_embeds_dashboard_metric_list():
    annotation = DashboardModule.model_fields["key_metrics"].annotation
    assert "DashboardMetric" in str(annotation), (
        "DashboardModule.key_metrics must remain typed as list[DashboardMetric]."
    )


def test_dashboard_summary_response_embeds_dashboard_module_map():
    annotation = DashboardSummaryResponse.model_fields["modules"].annotation
    assert "DashboardModule" in str(annotation), (
        "DashboardSummaryResponse.modules must remain typed as "
        "dict[str, DashboardModule]."
    )


def test_dashboard_evidence_table_response_embeds_evidence_rows():
    annotation = DashboardEvidenceTableResponse.model_fields["rows"].annotation
    assert "DashboardEvidenceRow" in str(annotation), (
        "DashboardEvidenceTableResponse.rows must remain typed as "
        "list[DashboardEvidenceRow]."
    )
