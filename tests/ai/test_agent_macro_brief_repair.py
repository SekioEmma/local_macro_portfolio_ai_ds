from __future__ import annotations

from typing import Any

from app_backend.schemas.macro_brief import (
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_MODULE_KEYS,
    MacroBrief,
)
from app_backend.services.agent_macro_brief_repair import repair_macro_brief_payload
from app_backend.services.claim_evidence_validator import validate_macro_brief_claim_evidence
from app_backend.services.macro_brief_evidence_projection import (
    project_macro_brief_sources_from_ledger,
)
from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
)


def _record(evidence_id: str = "ev_rate") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="run-1",
        tool_name="treasury_curve",
        source_kind="local_data_foundation",
        evidence_tier="local_data_foundation",
        title="Treasury curve 10Y",
        observation_date="2026-07-01",
        temporal_status="observed",
        atomic_observations=(
            AtomicObservation(value=4.3, unit="%", as_of="2026-07-01", series_id="DGS10"),
        ),
        public_visible=True,
    )


def _ledger() -> RunEvidenceLedger:
    return RunEvidenceLedger(run_id="run-1").add(_record())


def _payload(*, facts: list[dict[str, Any]]) -> dict[str, Any]:
    fact_ids = [fact["id"] for fact in facts if fact.get("evidence_ids")]
    return {
        "core_conclusion": "Macro pressure is watchful.",
        "market_state": [
            {"symbol": symbol, "price": None, "change_pct": None, "as_of": None}
            for symbol in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": facts,
        "judgments": [
            {
                "claim": "Rates remain the key pressure channel.",
                "evidence_supports": fact_ids,
                "evidence_ids": ["ev_rate"],
                "claim_type": "direct_evidence",
                "temporal_scope": "current_run",
            }
        ],
        "module_table": [
            {"module_key": key, "module_name_zh": key, "status": "watch", "note": None}
            for key in REQUIRED_MODULE_KEYS
        ],
        "risk_assessment": {
            "current_label": "watch",
            "summary": "Risk requires user review.",
            "upgrade_triggers": ["Inflation cools."],
            "downgrade_triggers": ["Rates rise further."],
        },
        "forward_indicators": [
            {"name": f"indicator_{idx}", "release_date": "2026-07-10", "relevance": "macro"}
            for idx in range(5)
        ],
        "scenarios": {
            key: {"trigger_conditions": ["macro trigger"], "transmission_path": "macro path"}
            for key in ("base", "bullish", "bearish", "systemic")
        },
        "source_list": [{"id": "fake", "accessed_at": "2026-07-01", "title": "fake"}],
        "boundary_notice": " / ".join(REQUIRED_BOUNDARY_KEYWORDS),
    }


def test_repair_fills_observed_fact_from_atomic_observation():
    payload = _payload(
        facts=[
            {
                "id": "f1",
                "statement": "10Y was around 4.9.",
                "value": 4.9,
                "unit": "%",
                "source_id": "fake",
                "evidence_ids": ["ev_rate"],
                "claim_status": "observed",
                "as_of": "2026-06-30",
            }
        ]
    )

    repaired = repair_macro_brief_payload(payload, _ledger())
    projected = project_macro_brief_sources_from_ledger(repaired.payload, _ledger())
    brief = MacroBrief.model_validate(projected)

    assert repaired.payload["confirmed_facts"][0]["value"] == 4.3
    assert repaired.payload["confirmed_facts"][0]["as_of"] == "2026-07-01"
    assert "observed_filled_from_atomic:f1" in repaired.actions
    assert validate_macro_brief_claim_evidence(brief, _ledger()) == []


def test_repair_drops_unavailable_or_unknown_evidence_facts_and_judgments():
    payload = _payload(
        facts=[
            {
                "id": "f1",
                "statement": "Known rate fact.",
                "value": 4.9,
                "unit": "%",
                "source_id": "fake",
                "evidence_ids": ["ev_rate"],
                "claim_status": "observed",
                "as_of": "2026-06-30",
            },
            {
                "id": "f2",
                "statement": "Unavailable QQQ quote.",
                "value": None,
                "unit": None,
                "source_id": "fake",
                "evidence_ids": [],
                "claim_status": "unavailable",
                "as_of": None,
            },
            {
                "id": "f3",
                "statement": "Unknown source.",
                "value": None,
                "unit": None,
                "source_id": "fake",
                "evidence_ids": ["missing"],
                "claim_status": "reported",
                "as_of": None,
            },
        ]
    )

    repaired = repair_macro_brief_payload(payload, _ledger())

    assert [fact["id"] for fact in repaired.payload["confirmed_facts"]] == ["f1"]
    assert "drop_fact_without_known_evidence:f2" in repaired.actions
    assert "drop_fact_without_known_evidence:f3" in repaired.actions
    assert repaired.payload["judgments"][0]["evidence_supports"] == ["f1"]


def test_repair_clears_invalid_reported_structured_value():
    payload = _payload(
        facts=[
            {
                "id": "f1",
                "statement": "Reported rate context.",
                "value": 9.9,
                "unit": "%",
                "source_id": "fake",
                "evidence_ids": ["ev_rate"],
                "claim_status": "reported",
                "as_of": "2026-07-01",
            }
        ]
    )

    repaired = repair_macro_brief_payload(payload, _ledger())
    fact = repaired.payload["confirmed_facts"][0]

    assert fact["claim_status"] == "reported"
    assert fact["value"] is None
    assert fact["unit"] is None
    assert fact["as_of"] is None
    assert "reported_cleared_mismatched_value:f1" in repaired.actions
