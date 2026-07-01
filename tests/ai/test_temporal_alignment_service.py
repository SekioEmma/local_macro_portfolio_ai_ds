from __future__ import annotations

from app_backend.services.run_evidence_ledger import EvidenceRecord, RunEvidenceLedger
from app_backend.services.temporal_alignment_service import build_temporal_envelope


def _record(
    evidence_id: str,
    *,
    tool_name: str,
    source_kind: str,
    observation_date: str | None = None,
    release_date: str | None = None,
    accessed_at: str = "2026-06-30T12:00:00+00:00",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="run1",
        tool_name=tool_name,
        source_kind=source_kind,
        evidence_tier="official_evidence",
        title=f"Evidence {evidence_id}",
        observation_date=observation_date,
        release_date=release_date,
        accessed_at=accessed_at,
        temporal_status="observed",
    )


def _ledger(*records: EvidenceRecord) -> RunEvidenceLedger:
    ledger = RunEvidenceLedger(run_id="run1")
    for record in records:
        ledger = ledger.add(record)
    return ledger


def test_temporal_envelope_collects_cutoff_dates_by_evidence_family():
    ledger = _ledger(
        _record(
            "ev_market_old",
            tool_name="quote_etf",
            source_kind="official_primary",
            observation_date="2026-06-28",
        ),
        _record(
            "ev_market_new",
            tool_name="treasury_curve",
            source_kind="official_primary",
            observation_date="2026-06-29",
        ),
        _record(
            "ev_policy",
            tool_name="rag_retrieve",
            source_kind="official_primary",
            observation_date="2026-06-15",
            release_date="2026-06-18",
        ),
        _record(
            "ev_news",
            tool_name="search_tavily",
            source_kind="public_reporting",
            observation_date="2026-06-30T12:00:00Z",
            accessed_at="2026-06-30T13:00:00+00:00",
        ),
    )

    envelope = build_temporal_envelope(
        ledger,
        report_generated_at="2026-06-30T14:00:00+00:00",
    )

    assert envelope.report_generated_at == "2026-06-30T14:00:00+00:00"
    assert envelope.market_data_cutoff == "2026-06-29"
    assert envelope.policy_data_cutoff == "2026-06-18"
    assert envelope.macro_data_cutoff == "2026-06-15"
    assert envelope.public_news_cutoff == "2026-06-30T12:00:00Z"
    assert envelope.asynchronous_inputs is False


def test_temporal_envelope_handles_empty_ledger():
    envelope = build_temporal_envelope(
        RunEvidenceLedger(run_id="run1"),
        report_generated_at="2026-06-30T14:00:00+00:00",
    )

    assert envelope.market_data_cutoff is None
    assert envelope.policy_data_cutoff is None
    assert envelope.macro_data_cutoff is None
    assert envelope.public_news_cutoff is None


def test_temporal_envelope_flags_market_data_trading_day_mismatch():
    ledger = _ledger(
        _record(
            "ev_market_old",
            tool_name="quote_etf",
            source_kind="official_primary",
            observation_date="2026-06-24",
        ),
        _record(
            "ev_market_new",
            tool_name="treasury_curve",
            source_kind="official_primary",
            observation_date="2026-06-29",
        ),
    )

    envelope = build_temporal_envelope(
        ledger,
        report_generated_at="2026-06-30T14:00:00+00:00",
    )

    assert envelope.max_market_data_age_trading_days == 3
    assert envelope.asynchronous_inputs is True
    assert "时间错配" in (envelope.temporal_alignment_note or "")
    assert "工作日跨度近似值" in (envelope.temporal_alignment_note or "")
