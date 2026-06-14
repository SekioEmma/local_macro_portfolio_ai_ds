from types import SimpleNamespace

import pytest

from modeling.evidence_index import EvidenceIndex, MissingEvidenceError


def test_evidence_index_finds_rows_by_metric_module_status_and_source():
    rows = [
        _row("credit_stress", "high_yield_spread", 3.4, source_badge="official"),
        _row("rate_pressure", "dgs10", 4.5, source_badge="official"),
        _row("credit_stress", "vix", 18.0, source_badge="proxy", status="watch"),
    ]
    index = EvidenceIndex(rows)

    assert index.by_metric_key("dgs10")["value"] == 4.5
    assert index.require_metric("high_yield_spread")["module"] == "credit_stress"
    assert len(index.rows_by_module("credit_stress")) == 2
    assert len(index.rows_by_source_badge("official")) == 2
    assert len(index.rows_by_status("watch")) == 1
    with pytest.raises(MissingEvidenceError):
        index.require_metric("missing_metric")


def test_evidence_index_blocks_bad_statuses_from_support():
    rows = [
        _row("credit_stress", "missing_metric", None, status="missing"),
        _row("credit_stress", "stale_metric", 1.0, freshness_status="stale"),
        _row("credit_stress", "research_metric", 1.0, status="research_needed"),
        _row("credit_stress", "history_metric", 1.0, status="insufficient_history"),
        _row("credit_stress", "not_available_metric", 1.0, status="not_available"),
        _row("credit_stress", "insufficient_metric", 1.0, status="insufficient_evidence"),
    ]
    index = EvidenceIndex(rows)

    for row in rows:
        metric_key = row["metric_key"]
        assert index.is_usable_for_support(metric_key) is False
        assert index.blocked_reason(metric_key) is not None


def test_evidence_index_does_not_treat_missing_as_low_pressure():
    index = EvidenceIndex([_row("credit_stress", "credit_stress_status", None, status="missing")])

    assert index.has_valid_value("credit_stress_status") is False
    assert index.is_usable_for_support("credit_stress_status") is False
    assert index.missing_or_blocked_inputs(["credit_stress_status"]) == [
        "credit_stress_status"
    ]


def test_evidence_index_respects_ai_context_allowed_and_proxy_trigger_gate():
    rows = [
        _row("credit_stress", "high_yield_spread", 3.4, ai_context_allowed=False),
        _row(
            "breadth_concentration_proxy",
            "hyg_vs_lqd_30d",
            -1.2,
            source_badge="proxy",
            trigger_eligibility="proxy_auxiliary_only",
        ),
        SimpleNamespace(
            module="rate_pressure",
            metric_key="dgs10",
            value=4.5,
            value_text="4.5%",
            status="ok",
            source_badge="official",
            freshness_status="fresh",
            ai_context_allowed=True,
        ),
    ]
    index = EvidenceIndex(rows)

    assert index.is_usable_for_support("high_yield_spread") is False
    assert index.blocked_reason("high_yield_spread") == "ai_context_not_allowed"
    assert index.is_usable_for_support(
        "hyg_vs_lqd_30d",
        require_core_trigger=True,
    ) is False
    assert index.is_usable_for_support("dgs10") is True
    assert len(index.rows_allowed_for_ai_context()) == 2
    assert len(index.rows_blocked_from_ai_context()) == 1
    assert index.public_payload("dgs10")["metric_key"] == "dgs10"


def _row(
    module,
    metric_key,
    value,
    *,
    status="ok",
    source_badge="official",
    freshness_status="fresh",
    ai_context_allowed=True,
    trigger_eligibility=None,
):
    return {
        "row_id": f"{module}:{metric_key}",
        "module": module,
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value,
        "value_text": str(value) if value is not None else status,
        "unit": None,
        "status": status,
        "source": "test_source",
        "source_badge": source_badge,
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": freshness_status,
        "missing_reason": None,
        "interpretation_hint": "test",
        "ai_context_allowed": ai_context_allowed,
        "trigger_eligibility": trigger_eligibility,
    }
