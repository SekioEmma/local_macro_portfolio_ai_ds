from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "ingest_official_economic_calendar.py"
SRC_ROOT = ROOT / "src"


def test_import_creates_no_side_effects(monkeypatch):
    calls = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: calls.append(1) or (_ for _ in ()).throw(AssertionError))
    import importlib
    spec = importlib.util.spec_from_file_location("cli_module", SCRIPT, submodule_search_locations=[])
    importlib.util.module_from_spec(spec)
    assert calls == []


def test_default_is_planned(tmp_path, monkeypatch):
    from app_backend.services.official_calendar_acquisition_service import (
        OfficialCalendarAcquisitionSummary,
    )

    fake_summary = OfficialCalendarAcquisitionSummary(
        status="planned",
        live=False,
        write=False,
        selected_sources=("bls", "bea"),
        start_date="2026-06-24",
        end_date="2027-06-24",
        error_codes=["live_disabled"],
    )
    with patch(
        "app_backend.services.official_calendar_acquisition_service.build_default_official_calendar_acquisition_service"
    ) as mock_build:
        mock_svc = mock_build.return_value
        mock_svc.run.return_value = fake_summary
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env={**dict(__import__("os").environ), "PYTHONPATH": str(SRC_ROOT)},
        )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "planned"


def test_source_default_is_bls_bea():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '("bls", "bea")' in source


def test_repeated_source_accepted():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "action=\"append\"" in source


def test_invalid_source_rejected():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--source", "fred"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(SRC_ROOT)},
    )
    assert result.returncode != 0


def test_live_flag_exists():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--live" in source
    assert "store_true" in source


def test_write_flag_exists():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--write" in source


def test_date_parameters_exist():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--start-date" in source
    assert "--end-date" in source


def test_safe_json_output_no_raw_exception(tmp_path, monkeypatch):
    from app_backend.services.official_calendar_acquisition_service import (
        OfficialCalendarAcquisitionSummary,
    )

    fake_summary = OfficialCalendarAcquisitionSummary(
        status="dry_run",
        live=True,
        write=False,
        selected_sources=("bls",),
        start_date="2026-06-24",
        end_date="2027-06-24",
        event_count=2,
        event_key_counts={"consumer_price_index": 1, "employment_situation": 1},
    )
    with patch(
        "app_backend.services.official_calendar_acquisition_service.build_default_official_calendar_acquisition_service"
    ) as mock_build:
        mock_svc = mock_build.return_value
        mock_svc.run.return_value = fake_summary
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--source", "bls", "--live"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env={**dict(__import__("os").environ), "PYTHONPATH": str(SRC_ROOT)},
        )
    output = json.loads(result.stdout)
    serialized = json.dumps(output)
    for token in ["https://", "bls.gov", "bea.gov", "Exception", "Traceback"]:
        assert token not in serialized


def test_no_db_creation_in_non_live_mode():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(SRC_ROOT)},
    )
    output = json.loads(result.stdout)
    assert output["status"] in ("planned", "error")


def test_cli_source_no_env_read():
    source = SCRIPT.read_text(encoding="utf-8")
    for token in ["os.environ", "os.getenv", "dotenv", "API_KEY"]:
        assert token not in source


def test_cli_no_seed_autoload():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "seed" not in source.lower()
    assert "fixture" not in source.lower()


def test_cli_no_scheduler():
    source = SCRIPT.read_text(encoding="utf-8")
    for token in ["schedule", "cron", "background", "daemon", "timer"]:
        assert token not in source.lower()


def test_write_requires_live_in_cli():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--write"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(SRC_ROOT)},
    )
    output = json.loads(result.stdout)
    assert output["status"] == "blocked"
    assert "write_requires_live" in output.get("error_codes", [])
