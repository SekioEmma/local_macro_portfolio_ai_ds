from __future__ import annotations

from app_backend.services.agent_evidence_ledger_registration import (
    register_tool_result_evidence,
)
from app_backend.services.agent_tool_registry import ToolResult
from app_backend.services.run_evidence_ledger import RunEvidenceLedger


def test_registers_rag_institutional_view_as_reported_evidence():
    ledger = RunEvidenceLedger(run_id="run1")
    result = ToolResult(
        status="ok",
        content={
            "chunks": [
                {
                    "doc_id": "memo_doc",
                    "chunk_index": 0,
                    "title": "Institutional memo",
                    "doc_type": "research_report",
                    "evidence_tier": "institutional_view",
                    "is_official_source": False,
                    "release_date": "2026-06-10",
                    "observation_period": "2026-05",
                    "vintage": "as_released",
                    "text": "reported view",
                }
            ],
            "chunk_count": 1,
        },
    )

    registered = register_tool_result_evidence(
        ledger,
        tool_name="rag_retrieve",
        result=result,
    )

    evidence_id = registered.evidence_ids[0]
    record = registered.ledger.by_id()[evidence_id]
    chunk = registered.result.content["chunks"][0]
    assert chunk["evidence_id"] == evidence_id
    assert registered.result.content["registered_evidence_ids"] == [evidence_id]
    assert record.source_kind == "institutional_research"
    assert record.evidence_tier == "institutional_view"
    assert record.rag_doc_id == "memo_doc"
    assert record.temporal_status == "reported"
    assert record.release_date == "2026-06-10"
    assert record.observation_date == "2026-05"
    assert record.value_summary["vintage"] == "as_released"


def test_registers_search_results_as_public_reporting():
    ledger = RunEvidenceLedger(run_id="run1")
    result = ToolResult(
        status="ok",
        content={
            "results": [
                {
                    "url": "https://www.reuters.com/markets/rates",
                    "title": "Rates story",
                    "domain": "www.reuters.com",
                    "published_at": "2026-06-30T12:00:00Z",
                    "relevance_score": 0.91,
                }
            ],
            "result_count": 1,
        },
    )

    registered = register_tool_result_evidence(
        ledger,
        tool_name="search_tavily",
        result=result,
    )

    evidence_id = registered.evidence_ids[0]
    record = registered.ledger.by_id()[evidence_id]
    assert registered.result.content["results"][0]["evidence_id"] == evidence_id
    assert record.source_kind == "public_reporting"
    assert record.evidence_tier == "public_reporting"
    assert record.canonical_url == "https://www.reuters.com/markets/rates"
    assert record.observation_date == "2026-06-30"
    assert record.public_visible is True


def test_registers_treasury_curve_points_as_observed_local_data():
    ledger = RunEvidenceLedger(run_id="run1")
    result = ToolResult(
        status="ok",
        content={
            "points": [
                {
                    "tenor": "10Y",
                    "source_series": "DGS10",
                    "value": 4.3,
                    "observation_date": "2026-06-29",
                    "status": "ok",
                },
                {"tenor": "30Y", "source_series": "DGS30", "value": None},
            ],
            "status": "partial",
        },
    )

    registered = register_tool_result_evidence(
        ledger,
        tool_name="treasury_curve",
        result=result,
    )

    assert len(registered.evidence_ids) == 1
    record = registered.ledger.by_id()[registered.evidence_ids[0]]
    assert registered.result.content["points"][0]["evidence_id"] == record.evidence_id
    assert "evidence_id" not in registered.result.content["points"][1]
    assert record.source_kind == "local_data_foundation"
    assert record.evidence_tier == "local_data_foundation"
    assert record.series_id == "DGS10"
    assert record.canonical_url == "https://fred.stlouisfed.org/series/DGS10"
    assert record.temporal_status == "observed"
    assert record.atomic_observations[0].value == 4.3
    assert record.atomic_observations[0].unit == "%"
    assert record.atomic_observations[0].as_of == "2026-06-29"
    assert record.atomic_observations[0].series_id == "DGS10"


def test_error_tool_result_does_not_register_evidence():
    ledger = RunEvidenceLedger(run_id="run1")

    registered = register_tool_result_evidence(
        ledger,
        tool_name="treasury_curve",
        result=ToolResult(status="error", error_code="boom"),
    )

    assert registered.ledger.records == ()
    assert registered.evidence_ids == []
