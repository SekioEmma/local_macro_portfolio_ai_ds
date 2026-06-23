import subprocess
import sys
from pathlib import Path

import run_daily_report


def test_snapshot_generator_failure_prints_script_and_captured_output(monkeypatch, capsys):
    script_path = run_daily_report.PROJECT_ROOT / "scripts" / "broken_generator.py"

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=7,
            cmd=[sys.executable, str(script_path)],
            output="stdout clue\n",
            stderr="stderr clue\n",
        )

    monkeypatch.setattr(run_daily_report.subprocess, "run", fake_run)

    try:
        run_daily_report._run_snapshot_generator(script_path)
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("Expected snapshot generator failure")

    captured = capsys.readouterr()
    relative_script = script_path.relative_to(run_daily_report.PROJECT_ROOT)
    assert f"Snapshot generator failed: {relative_script}" in captured.err
    assert "stdout clue" in captured.err
    assert "stderr clue" in captured.err


def test_ensure_snapshot_files_reports_which_generator_failed(monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "snapshot.json"
    script_path = run_daily_report.PROJECT_ROOT / "scripts" / "failing_snapshot.py"

    monkeypatch.setattr(run_daily_report, "SNAPSHOT_GENERATORS", {output_path: script_path})
    monkeypatch.setattr(run_daily_report, "SNAPSHOT_MAX_AGE_SECONDS", {output_path: 1})

    def fake_run_snapshot_generator(path: Path) -> None:
        print(f"Snapshot generator failed: {path.relative_to(run_daily_report.PROJECT_ROOT)}", file=sys.stderr)
        raise subprocess.CalledProcessError(returncode=3, cmd=[sys.executable, str(path)])

    monkeypatch.setattr(run_daily_report, "_run_snapshot_generator", fake_run_snapshot_generator)

    try:
        run_daily_report._ensure_snapshot_files()
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("Expected snapshot generator failure")

    relative_script = script_path.relative_to(run_daily_report.PROJECT_ROOT)
    assert str(relative_script) in capsys.readouterr().err
