from __future__ import annotations

from typing import Any

from app_backend.schemas.macro_brief import (
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_MODULE_KEYS,
    MacroBrief,
)
from app_backend.services.claim_evidence_validator import (
    validate_macro_brief_claim_evidence,
)
from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
)


def _record(
    evidence_id: str,
    *,
    source_kind: str = "official_primary",
    evidence_tier: str = "official_evidence",
    temporal_status: str = "observed",
    value: float = 4.3,
    unit: str | None = "%",
    as_of: str = "2026-06-29",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="run1",
        tool_name="treasury_curve",
        source_kind=source_kind,
        evidence_tier=evidence_tier,
        title=f"Evidence {evidence_id}",
        observation_date=as_of,
        release_date=as_of,
        accessed_at="2026-06-30T12:00:00+00:00",
        temporal_status=temporal_status,
        atomic_observations=(
            AtomicObservation(value=value, unit=unit, as_of=as_of, series_id="DGS10"),
        ),
        public_visible=True,
    )


def _ledger(*records: EvidenceRecord) -> RunEvidenceLedger:
    ledger = RunEvidenceLedger(run_id="run1")
    for record in records:
        ledger = ledger.add(record)
    return ledger


def _brief_payload(
    *,
    facts: list[dict[str, Any]] | None = None,
    judgments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "core_conclusion": "Macro environment remains balanced.",
        "market_state": [
            {"symbol": symbol, "price": 100.0, "change_pct": 0.1, "as_of": "2026-06-29"}
            for symbol in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": facts
        or [
            {
                "id": "f1",
                "statement": "DGS10 was observed.",
                "value": 4.3,
                "unit": "%",
                "source_id": "s1",
                "evidence_ids": ["ev_observed"],
                "claim_status": "observed",
                "as_of": "2026-06-29",
            }
        ],
        "judgments": judgments
        or [
            {
                "claim": "Rates remain the main pressure channel.",
                "evidence_supports": ["f1"],
                "evidence_ids": ["ev_observed"],
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
            "summary": "Balanced risk.",
            "upgrade_triggers": ["Credit spreads widen."],
            "downgrade_triggers": ["Inflation cools."],
        },
        "forward_indicators": [
            {"name": f"indicator_{idx}", "release_date": "2026-07-10", "relevance": "macro"}
            for idx in range(5)
        ],
        "scenarios": {
            key: {"trigger_conditions": ["macro trigger"], "transmission_path": "macro path"}
            for key in ("base", "bullish", "bearish", "systemic")
        },
        "source_list": [
            {
                "id": "s1",
                "url": "https://fred.stlouisfed.org/series/DGS10",
                "accessed_at": "2026-06-30",
            }
        ],
        "boundary_notice": " / ".join(REQUIRED_BOUNDARY_KEYWORDS),
    }


def _brief(**overrides: Any) -> MacroBrief:
    return MacroBrief.model_validate(_brief_payload(**overrides))


def test_observed_fact_with_official_observed_evidence_passes():
    findings = validate_macro_brief_claim_evidence(
        _brief(),
        _ledger(_record("ev_observed")),
    )

    assert findings == []


def test_observed_fact_rejects_value_that_does_not_match_atomic_observation():
    facts = _brief_payload()["confirmed_facts"]
    facts[0]["value"] = 4.9

    findings = validate_macro_brief_claim_evidence(
        _brief(facts=facts),
        _ledger(_record("ev_observed")),
    )

    assert findings == ["confirmed_facts[f1].atomic_observation_mismatch"]


def test_observed_fact_rejects_as_of_that_does_not_match_atomic_observation():
    facts = _brief_payload()["confirmed_facts"]
    facts[0]["as_of"] = "2026-06-28"

    findings = validate_macro_brief_claim_evidence(
        _brief(facts=facts),
        _ledger(_record("ev_observed")),
    )

    assert findings == ["confirmed_facts[f1].atomic_observation_mismatch"]


def test_reported_fact_does_not_require_atomic_observation_binding():
    facts = _brief_payload()["confirmed_facts"]
    facts[0]["claim_status"] = "reported"
    facts[0]["value"] = 9.9

    findings = validate_macro_brief_claim_evidence(
        _brief(facts=facts),
        _ledger(
            _record(
                "ev_observed",
                source_kind="public_reporting",
                evidence_tier="public_reporting",
                temporal_status="reported",
            ).model_copy(update={"atomic_observations": ()})
        ),
    )

    assert findings == []


def test_fact_unknown_evidence_id_is_reported():
    findings = validate_macro_brief_claim_evidence(
        _brief(),
        _ledger(_record("ev_other")),
    )

    assert findings == [
        "confirmed_facts[f1].unknown_evidence_ids:ev_observed",
        "judgments[0].unknown_evidence_ids:ev_observed",
    ]


def test_observed_fact_rejects_reported_institutional_view_as_observation():
    findings = validate_macro_brief_claim_evidence(
        _brief(),
        _ledger(
            _record(
                "ev_observed",
                source_kind="institutional_research",
                evidence_tier="institutional_view",
                temporal_status="reported",
            )
        ),
    )

    assert "confirmed_facts[f1].observed_without_observed_evidence" in findings
    assert "confirmed_facts[f1].observed_uses_institutional_view" in findings


def test_reported_institutional_fact_allows_institutional_research_source():
    facts = _brief_payload()["confirmed_facts"]
    facts[0]["claim_status"] = "reported"

    findings = validate_macro_brief_claim_evidence(
        _brief(facts=facts),
        _ledger(
            _record(
                "ev_observed",
                source_kind="institutional_research",
                evidence_tier="institutional_view",
                temporal_status="reported",
            )
        ),
    )

    assert findings == []


def test_reported_institutional_fact_flags_source_kind_mismatch():
    facts = _brief_payload()["confirmed_facts"]
    facts[0]["claim_status"] = "reported"

    findings = validate_macro_brief_claim_evidence(
        _brief(facts=facts),
        _ledger(
            _record(
                "ev_observed",
                source_kind="public_reporting",
                evidence_tier="institutional_view",
                temporal_status="reported",
            )
        ),
    )

    assert findings == ["confirmed_facts[f1].institutional_view_source_kind_mismatch"]


def test_judgment_unknown_evidence_id_is_reported():
    judgments = _brief_payload()["judgments"]
    judgments[0]["evidence_ids"] = ["ev_missing"]

    findings = validate_macro_brief_claim_evidence(
        _brief(judgments=judgments),
        _ledger(_record("ev_observed")),
    )

    assert findings == ["judgments[0].unknown_evidence_ids:ev_missing"]
