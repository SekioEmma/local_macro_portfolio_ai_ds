from __future__ import annotations

from app_backend.schemas.macro_brief import ConfirmedFact
from app_backend.services.agent_evidence_pack import build_evidence_pack
from app_backend.services.agent_tool_plan_runner import PlannedToolOutcome
from app_backend.services.claim_evidence_validator import _validate_fact_records
from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
)


def test_evidence_pack_builds_observed_candidate_from_atomic_observation():
    record = EvidenceRecord(
        evidence_id="ev_spy",
        run_id="run-1",
        tool_name="quote_etf",
        source_kind="local_data_foundation",
        evidence_tier="local_data_foundation",
        title="ETF quote SPY",
        series_id="SPY",
        observation_date="2026-07-01",
        temporal_status="observed",
        value_summary={"symbol": "SPY", "value": 500.25, "unit": "USD"},
        atomic_observations=(
            AtomicObservation(value=500.25, unit="USD", as_of="2026-07-01", series_id="SPY"),
        ),
    )
    ledger = RunEvidenceLedger(run_id="run-1").add(record)

    pack = build_evidence_pack(ledger=ledger, outcomes=[])

    fact = pack.candidate_facts[0]
    assert fact.claim_status == "observed"
    assert fact.value == 500.25
    assert fact.unit == "USD"
    assert fact.as_of == "2026-07-01"
    assert fact.evidence_ids == ["ev_spy"]
    assert _validate_fact_records(
        ConfirmedFact(**fact.to_macro_brief_fact()),
        [record],
    ) == []


def test_evidence_pack_uses_reported_null_fact_for_non_atomic_record():
    record = EvidenceRecord(
        evidence_id="ev_news",
        run_id="run-1",
        tool_name="search_tavily",
        source_kind="public_reporting",
        evidence_tier="public_reporting",
        title="Reuters macro report",
        canonical_url="https://example.test/report",
        release_date="2026-07-01",
        temporal_status="reported",
        value_summary={"status": "reported"},
    )
    ledger = RunEvidenceLedger(run_id="run-1").add(record)

    pack = build_evidence_pack(ledger=ledger, outcomes=[])

    fact = pack.candidate_facts[0]
    assert fact.claim_status == "reported"
    assert fact.value is None
    assert fact.unit is None
    assert fact.as_of is None
    assert _validate_fact_records(
        ConfirmedFact(**fact.to_macro_brief_fact()),
        [record],
    ) == []


def test_evidence_pack_tracks_unavailable_tool_topics_without_raw_content():
    outcome = PlannedToolOutcome(
        topic="energy",
        tool_name="commodity_quote",
        status="error",
        required=False,
        error_code="handler_exception",
        error_message="redacted",
    )

    pack = build_evidence_pack(ledger=RunEvidenceLedger(run_id="run-1"), outcomes=[outcome])

    assert pack.unavailable_topics == ["energy"]
    assert pack.tool_outcomes == [
        {
            "topic": "energy",
            "tool_name": "commodity_quote",
            "status": "error",
            "required": False,
            "error_code": "handler_exception",
            "evidence_ids": [],
        }
    ]


def test_evidence_pack_tracks_ok_but_unavailable_tool_topics():
    outcomes = [
        PlannedToolOutcome(
            topic="local_rag_context",
            tool_name="rag_retrieve",
            status="ok",
            content={
                "chunks": [],
                "chunk_count": 0,
                "status": "unavailable",
                "reason_code": "index_generation_missing_or_invalid",
            },
        ),
        PlannedToolOutcome(
            topic="current_public_news",
            tool_name="search_tavily",
            status="ok",
            content={"results": [], "result_count": 0},
            required=False,
        ),
    ]

    pack = build_evidence_pack(ledger=RunEvidenceLedger(run_id="run-1"), outcomes=outcomes)

    assert pack.unavailable_topics == ["local_rag_context", "current_public_news"]
