from __future__ import annotations

import json
from pathlib import Path

from scripts import run_phase_f_controlled_agent_smoke as smoke


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase_f_critical_path_controlled_agent_smoke_passes(tmp_path):
    result = smoke.run_controlled_smoke(trace_dir=tmp_path)

    assert result["check_status"] == "passed"
    assert result["final_status"] == "ok"
    assert result["failed_checks"] == []
    assert result["warning_codes"] == []
    assert result["include_holdings"] is False
    assert result["external_search_confirmed"] is False
    record = result["validation_record"]
    assert record["acceptance_questions"] == list(smoke.ACCEPTANCE_QUESTIONS)
    assert record["tool_call_sequence"] == ["treasury_curve", "finalize_macro_brief"]
    assert record["cutoffs"]["market_data_cutoff"] == "2026-06-29"
    assert record["evidence_counts"] == {
        "total": 1,
        "official": 0,
        "public": 0,
        "institutional": 0,
        "local_data_foundation": 1,
        "licensed_manual_data": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    assert record["unavailable_modules"] == []
    assert record["asynchronous_inputs"] is False


def test_phase_f_release_gate_is_documented_and_wired_to_ci():
    checklist = (_REPO_ROOT / "docs" / "infra" / "phase_f_release_checklist.md").read_text(encoding="utf-8")
    index = (_REPO_ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    roadmap = (_REPO_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    governance = (_REPO_ROOT / "docs" / "GOVERNANCE.md").read_text(encoding="utf-8")
    phase_plan = (_REPO_ROOT / "docs" / "era2_phase_f_plan.md").read_text(encoding="utf-8")
    ci = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "run_phase_f_controlled_agent_smoke.py" in checklist
    assert "--report-path" in checklist
    assert "run_phase_f_controlled_agent_smoke.py" in roadmap
    assert "run_phase_f_controlled_agent_smoke.py" in phase_plan
    assert "run_phase_f_controlled_agent_smoke.py" in ci
    assert "phase_f_release_checklist.md" in governance
    assert "phase_f_release_checklist.md" in index
    assert "phase_f_release_checklist.md" in phase_plan
    assert "remediation_and_optimization" in checklist
    assert "remediation_and_optimization" in index
    assert "remediation_and_optimization" in phase_plan
    assert "not user_accepted" in checklist
    assert "user_accepted" in index
    assert "not user_accepted" in phase_plan
    assert "not production_ready" in checklist
    assert "production_ready" in index
    assert "not production_ready" in phase_plan
    assert "研究辅助输出" in checklist
    assert "非自动投资决策" in checklist
    assert "需要用户审阅" in checklist


def test_phase_f_controlled_run_reports_are_recorded():
    fixture_report = json.loads(
        (_REPO_ROOT / "docs" / "infra" / "phase_f_controlled_run_fixture_latest.json").read_text(encoding="utf-8")
    )
    live_report = json.loads(
        (_REPO_ROOT / "docs" / "infra" / "phase_f_controlled_run_live_latest.json").read_text(encoding="utf-8")
    )

    for report in (fixture_report, live_report):
        record = report["validation_record"]
        assert report["check_status"] == "passed"
        assert report["final_status"] == "ok"
        assert report["warning_codes"] == []
        assert report["include_holdings"] is False
        assert report["external_search_confirmed"] is False
        assert record["acceptance_questions"] == list(smoke.ACCEPTANCE_QUESTIONS)
        assert record["tool_call_sequence"] == ["treasury_curve", "finalize_macro_brief"]
        assert record["evidence_count"] == 1
        assert record["evidence_counts"]["total"] == 1
        assert record["evidence_counts"]["local_data_foundation"] == 1
        assert record["budget_usage"]["warning_count"] == 0

    assert live_report["mode"] == "live"
    assert "market_state:SPY" in live_report["validation_record"]["unavailable_modules"]


def test_phase_f_dod_audit_covers_required_gates():
    audit = (_REPO_ROOT / "docs" / "infra" / "phase_f_dod_audit.md").read_text(encoding="utf-8")
    checklist = (_REPO_ROOT / "docs" / "infra" / "phase_f_release_checklist.md").read_text(encoding="utf-8")
    index = (_REPO_ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")

    required_items = [
        "文档权威层级已生效",
        "所有 ADR 已 accepted",
        "详细 holdings consent 已实现并通过安全测试",
        "Institution MEMO rights gate 已实现",
        "Claim-Evidence Ledger 已实现",
        "Temporal Alignment Gate 已实现",
        "SSE 已实现",
        "Trace 长期保存已实现",
        "RAG generation contract 已实现",
        "所有关键测试通过",
        "真实受控 Agent run 验收通过",
        "ROADMAP、Governance、Phase Plan、API、前端行为一致",
    ]
    for item in required_items:
        assert item in audit
    assert "phase_f_dod_audit.md" in checklist
    assert "phase_f_dod_audit.md" in index
    assert "not user_accepted" in audit
    assert "not production_ready" in audit
