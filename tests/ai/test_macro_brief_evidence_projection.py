from __future__ import annotations

from app_backend.services.macro_brief_evidence_projection import (
    project_macro_brief_sources_from_ledger,
)
from app_backend.services.run_evidence_ledger import EvidenceRecord, RunEvidenceLedger


def _record(evidence_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="run1",
        tool_name="treasury_curve",
        source_kind="official_primary",
        evidence_tier="official_evidence",
        title="DGS10",
        canonical_url="https://fred.stlouisfed.org/series/DGS10",
        accessed_at="2026-06-30T12:00:00+00:00",
        temporal_status="observed",
    )


def test_project_macro_brief_sources_from_ledger_overrides_llm_sources():
    ledger = RunEvidenceLedger(run_id="run1").add(_record("ev_dgs10"))
    payload = {
        "confirmed_facts": [
            {
                "id": "f1",
                "statement": "DGS10 was elevated.",
                "source_id": "llm_source",
                "evidence_ids": ["ev_dgs10"],
            }
        ],
        "judgments": [{"claim": "x", "evidence_supports": ["f1"], "evidence_ids": ["ev_dgs10"]}],
        "source_list": [
            {
                "id": "llm_source",
                "url": "https://example.com/not-used",
                "accessed_at": "2026-01-01",
            }
        ],
    }

    projected = project_macro_brief_sources_from_ledger(payload, ledger)

    assert projected["confirmed_facts"][0]["source_id"] == "src_ev_dgs10"
    assert projected["source_list"] == [
        {
            "id": "src_ev_dgs10",
            "url": "https://fred.stlouisfed.org/series/DGS10",
            "rag_doc_id": None,
            "accessed_at": "2026-06-30T12:00:00+00:00",
            "title": "DGS10",
        }
    ]


def test_project_macro_brief_sources_uses_stable_short_ids_for_long_evidence_ids():
    long_id = "ev_" + "x" * 120
    ledger = RunEvidenceLedger(run_id="run1").add(_record(long_id))
    projected = project_macro_brief_sources_from_ledger(
        {
            "confirmed_facts": [{"id": "f1", "source_id": "s1", "evidence_ids": [long_id]}],
            "judgments": [],
        },
        ledger,
    )

    source_id = projected["confirmed_facts"][0]["source_id"]
    assert source_id.startswith("src_")
    assert len(source_id) <= 64
    assert projected["source_list"][0]["id"] == source_id
