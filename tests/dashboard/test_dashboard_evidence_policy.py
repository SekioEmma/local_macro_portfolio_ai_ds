from pathlib import Path

from app_backend.schemas.responses import DashboardMetric
from app_backend.services import dashboard_evidence_policy as policy
from app_backend.services import dashboard_service


def test_build_evidence_row_preserves_optional_fields():
    metric = _metric(
        input_evidence=[{"metric_key": "dgs10", "value": 4.5}],
        component_contributions={"rates": {"score": 1}},
        missing_inputs=["credit_spread"],
        interpretation_boundary="Boundary text.",
        lookback_window="5Y rolling",
        lookback_start="2021-01-01",
        lookback_end="2026-01-01",
        observation_count=1200,
        minimum_observation_count=60,
        history_quality_status="sufficient",
        percentile=0.91,
        percentile_band="high",
        zscore=1.5,
        zscore_band="elevated",
        robust_zscore=2.1,
        robust_zscore_band="high",
        percentile_direction="higher_is_more_stress",
        frequency_class="daily",
        transform_class="level",
        ai_context_tier="model_output",
        trigger_eligibility="reference_review_only",
    )

    row = policy.build_evidence_row("test_module", metric)

    assert row.row_id == "test_module:test_metric"
    assert row.module == "test_module"
    assert row.metric_key == metric.metric_key
    assert row.display_name == metric.display_name
    assert row.value == metric.value
    assert row.value_text == metric.value_text
    assert row.unit == metric.unit
    assert row.status == metric.status
    assert row.source == metric.source
    assert row.source_badge == metric.source_badge
    assert row.source_series == metric.source_series
    assert row.observation_date == metric.observation_date
    assert row.generated_at == metric.generated_at
    assert row.freshness_status == metric.freshness_status
    assert row.missing_reason == metric.missing_reason
    assert row.interpretation_hint == metric.interpretation_hint
    assert row.input_evidence == metric.input_evidence
    assert row.component_contributions == metric.component_contributions
    assert row.missing_inputs == metric.missing_inputs
    assert row.interpretation_boundary == metric.interpretation_boundary
    assert row.lookback_window == metric.lookback_window
    assert row.lookback_start == metric.lookback_start
    assert row.lookback_end == metric.lookback_end
    assert row.observation_count == metric.observation_count
    assert row.minimum_observation_count == metric.minimum_observation_count
    assert row.history_quality_status == metric.history_quality_status
    assert row.percentile == metric.percentile
    assert row.percentile_band == metric.percentile_band
    assert row.zscore == metric.zscore
    assert row.zscore_band == metric.zscore_band
    assert row.robust_zscore == metric.robust_zscore
    assert row.robust_zscore_band == metric.robust_zscore_band
    assert row.percentile_direction == metric.percentile_direction
    assert row.frequency_class == metric.frequency_class
    assert row.transform_class == metric.transform_class
    assert row.ai_context_tier == metric.ai_context_tier
    assert row.trigger_eligibility == metric.trigger_eligibility


def test_ai_context_blocked_reason_precedence():
    assert _blocked(value=None, status="missing") == "value_missing"
    assert _blocked(status="missing", source_badge="missing") == "status_missing"
    assert _blocked(source_badge="missing", freshness_status="stale") == "source_badge_missing"
    assert _blocked(source_badge="official", freshness_status="stale") == "freshness_stale"
    assert _blocked(source_badge="proxy", freshness_status="fresh") == "source_badge_proxy"
    assert (
        _blocked(source_badge="commercial_api_fallback", freshness_status="fresh")
        == "source_badge_commercial_api_fallback"
    )
    assert (
        _blocked(source_badge="official_reference", freshness_status="fresh")
        is None
    )
    assert (
        _blocked(source_badge="derived", interpretation_hint="plain note")
        == "dependency_metadata_incomplete"
    )
    assert _blocked(source=None, source_badge="official") == "source_missing"
    assert (
        _blocked(source="test_source", source_badge="official", observation_date=None, generated_at=None)
        == "date_missing"
    )


def test_ppi_observation_date_block_sets_blocked_reason():
    for metric_key in ("ppi_final_demand", "ppi_final_demand_yoy"):
        metric = _metric(metric_key=metric_key, observation_date=None)

        row = policy.build_evidence_row("inflation_energy_pressure", metric)

        assert policy.evidence_ai_context_allowed(metric) is False
        assert row.ai_context_allowed is False
        assert row.blocked_reason == "observation_date_missing"


def test_local_freshness_exception_requires_generated_at():
    assert (
        _blocked(
            source="local_rules",
            source_badge="local",
            freshness_status="stale",
            generated_at="2026-01-01T00:00:00+00:00",
            observation_date=None,
        )
        is None
    )
    assert (
        _blocked(
            source="local_rules",
            source_badge="local",
            freshness_status="stale",
            generated_at=None,
            observation_date=None,
        )
        == "freshness_stale"
    )


def test_derived_dependency_hint_gate():
    for hint in (
        "Derived from source metrics.",
        "Uses historical observations.",
        "Compact dashboard context.",
    ):
        assert policy.derived_dependency_hint_complete(hint) is True
        assert _blocked(source_badge="derived", interpretation_hint=hint) is None

    assert policy.derived_dependency_hint_complete("plain note") is False
    assert (
        _blocked(source_badge="derived", interpretation_hint="plain note")
        == "dependency_metadata_incomplete"
    )


def test_missing_value_text_mapping():
    assert policy.missing_value_text("research_needed") == "research needed"
    assert policy.missing_value_text("insufficient_history") == "insufficient history"
    assert policy.missing_value_text("stale") == "stale"
    assert policy.missing_value_text("not_available") == "not available"
    assert policy.missing_value_text("unknown") == "unknown"
    assert policy.missing_value_text("missing") == "missing"
    assert policy.missing_value_text("ok") == "missing"


def test_dashboard_service_compatibility_aliases():
    assert dashboard_service._evidence_row is policy.build_evidence_row
    assert dashboard_service._evidence_value_text is policy.evidence_value_text
    assert dashboard_service._evidence_ai_context_allowed is policy.evidence_ai_context_allowed
    assert (
        dashboard_service._ppi_observation_date_blocked_reason
        is policy.ppi_observation_date_blocked_reason
    )
    assert dashboard_service._ai_context_allowed is policy.ai_context_allowed
    assert dashboard_service._ai_context_blocked_reason is policy.ai_context_blocked_reason
    assert dashboard_service._missing_value_text is policy.missing_value_text
    assert (
        dashboard_service._derived_dependency_hint_complete
        is policy.derived_dependency_hint_complete
    )


def test_new_policy_module_has_no_forbidden_surfaces():
    text = Path("src/app_backend/services/dashboard_evidence_policy.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/external",
        "DeepSeek",
        "Tavily",
        "external_llm.yaml",
        ".env",
        "scenario_probability",
        "forecast_path",
        "expected_return",
        "target_price",
        "portfolio_action",
        "trade_signal",
        "target_allocation",
        "buy",
        "sell",
        "hedge",
        "rebalance",
    ):
        assert token not in text


def _blocked(**overrides):
    params = {
        "status": "ok",
        "value": 1.0,
        "source": "test_source",
        "source_badge": "official",
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "interpretation_hint": None,
    }
    params.update(overrides)
    return policy.ai_context_blocked_reason(**params)


def _metric(**overrides):
    params = {
        "metric_key": "test_metric",
        "display_name": "Test metric",
        "value": 1.0,
        "value_text": "1.0",
        "unit": "index",
        "status": "ok",
        "source": "test_source",
        "source_badge": "official",
        "source_series": "TEST",
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": None,
        "ai_context_allowed": True,
    }
    params.update(overrides)
    return DashboardMetric(**params)
