from __future__ import annotations

import json

from scripts import run_phase_f_controlled_agent_smoke as smoke


def test_controlled_smoke_fixture_passes_without_external_search_or_holdings(tmp_path):
    result = smoke.run_controlled_smoke(trace_dir=tmp_path)

    assert result["check_status"] == "passed"
    assert result["final_status"] == "ok"
    assert result["failed_checks"] == []
    assert result["provider_call_count"] >= 2
    assert result["steps"] >= 2
    assert result["external_search_confirmed"] is False
    assert result["include_holdings"] is False


def test_controlled_smoke_cli_outputs_machine_readable_json(tmp_path, capsys):
    exit_code = smoke.main(["--trace-dir", str(tmp_path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["check_status"] == "passed"
    assert payload["session_id"] == smoke.CONTROLLED_SESSION_ID
    assert payload["warning_codes"] == []
