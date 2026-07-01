from __future__ import annotations

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
    roadmap = (_REPO_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    governance = (_REPO_ROOT / "docs" / "GOVERNANCE.md").read_text(encoding="utf-8")
    phase_plan = (_REPO_ROOT / "docs" / "era2_phase_f_plan.md").read_text(encoding="utf-8")
    ci = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "run_phase_f_controlled_agent_smoke.py" in checklist
    assert "run_phase_f_controlled_agent_smoke.py" in roadmap
    assert "run_phase_f_controlled_agent_smoke.py" in phase_plan
    assert "run_phase_f_controlled_agent_smoke.py" in ci
    assert "phase_f_release_checklist.md" in governance
    assert "phase_f_release_checklist.md" in phase_plan
    assert "remediation_and_optimization" in checklist
    assert "remediation_and_optimization" in phase_plan
    assert "not user_accepted" in checklist
    assert "not user_accepted" in phase_plan
    assert "not production_ready" in checklist
    assert "not production_ready" in phase_plan
    assert "研究辅助输出" in checklist
    assert "非自动投资决策" in checklist
    assert "需要用户审阅" in checklist
