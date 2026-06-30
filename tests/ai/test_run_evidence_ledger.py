from __future__ import annotations

import pytest

from app_backend.services.run_evidence_ledger import (
    EvidenceRecord,
    RunEvidenceLedger,
    sha256_json_summary,
)


def _record(evidence_id: str = "ev1", run_id: str = "run1") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id=run_id,
        tool_name="quote_etf",
        source_kind="official_primary",
        evidence_tier="official_evidence",
        title="SPY quote",
        observation_date="2026-06-29",
        accessed_at="2026-06-30T12:00:00+00:00",
        temporal_status="observed",
        public_visible=True,
    )


def test_ledger_add_returns_new_immutable_ledger():
    ledger = RunEvidenceLedger(run_id="run1")
    updated = ledger.add(_record())

    assert ledger.records == ()
    assert [record.evidence_id for record in updated.records] == ["ev1"]
    assert updated.by_id()["ev1"].tool_name == "quote_etf"


def test_ledger_rejects_duplicate_evidence_id():
    ledger = RunEvidenceLedger(run_id="run1").add(_record())

    with pytest.raises(ValueError, match="duplicate evidence_id"):
        ledger.add(_record())


def test_ledger_rejects_cross_run_record():
    ledger = RunEvidenceLedger(run_id="run1")

    with pytest.raises(ValueError, match="run_id does not match"):
        ledger.add(_record(run_id="run2"))


def test_sha256_json_summary_is_order_stable():
    left = {"b": 2, "a": {"z": 1}}
    right = {"a": {"z": 1}, "b": 2}

    assert sha256_json_summary(left) == sha256_json_summary(right)
    assert len(sha256_json_summary(left)) == 64
