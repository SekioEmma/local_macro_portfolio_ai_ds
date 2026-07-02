from __future__ import annotations

from datetime import date

from app_backend.services.agent_evidence_pack import CandidateFact, EvidenceCard, EvidencePack
from app_backend.services.agent_evidence_writer import build_evidence_writer_prompt
from app_backend.services.run_evidence_ledger import AtomicObservation


def _pack() -> EvidencePack:
    return EvidencePack(
        cards=[
            EvidenceCard(
                evidence_id="ev_spy",
                tool_name="quote_etf",
                title="ETF quote SPY",
                evidence_tier="local_data_foundation",
                source_kind="local_data_foundation",
                temporal_status="observed",
                as_of="2026-07-01",
                value_summary={"symbol": "SPY", "value": 500.25, "unit": "USD"},
                atomic_observations=[
                    AtomicObservation(value=500.25, unit="USD", as_of="2026-07-01")
                ],
                public_visible=True,
            )
        ],
        candidate_facts=[
            CandidateFact(
                id="cf1",
                statement="ETF quote SPY; value 500.25 USD as of 2026-07-01",
                evidence_ids=["ev_spy"],
                claim_status="observed",
                value=500.25,
                unit="USD",
                as_of="2026-07-01",
            )
        ],
        unavailable_topics=["energy"],
    )


def test_strict_writer_prompt_constrains_facts_and_sources():
    prompt = build_evidence_writer_prompt(
        user_question="当前宏观环境如何？",
        current_date=date(2026, 7, 1),
        evidence_pack=_pack(),
        output_mode="macro_brief_strict",
    )

    text = "\n".join(message.content for message in prompt.messages)

    assert prompt.response_format == {"type": "json_object"}
    assert "confirmed_facts must be copied from candidate_facts" in text
    assert "Do not hand-author source_list content" in text
    assert "ev_spy" in text
    assert "cf1" in text
    assert "energy" in text


def test_natural_writer_prompt_is_not_schema_bound_but_keeps_boundaries():
    prompt = build_evidence_writer_prompt(
        user_question="private wording should not matter",
        current_date=date(2026, 7, 1),
        evidence_pack=_pack(),
        output_mode="natural_answer",
    )

    text = "\n".join(message.content for message in prompt.messages)

    assert prompt.response_format is None
    assert "Write in natural, readable Chinese" in text
    assert "Use exact evidence_id strings copied from evidence_cards" in text
    assert "Never invent aliases" in text
    assert "非个股操作" in text
    assert "ev_spy" in text
