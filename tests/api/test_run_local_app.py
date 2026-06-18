from __future__ import annotations

import os
from pathlib import Path

import run_local_app


def test_launcher_uses_fixed_local_service_urls():
    assert run_local_app.HOST == "127.0.0.1"
    assert run_local_app.BACKEND_STATUS_URL == "http://127.0.0.1:8765/api/status"
    assert run_local_app.FRONTEND_URL == "http://127.0.0.1:5173"


def test_launcher_uses_current_python_and_frontend_working_directory(monkeypatch):
    calls = []

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(command, *, cwd, creationflags):
        calls.append((command, cwd, creationflags))
        return FakeProcess()

    monkeypatch.setattr(run_local_app.subprocess, "Popen", fake_popen)

    backend = run_local_app._start_process(
        "Backend",
        [
            run_local_app.sys.executable,
            str(run_local_app.PROJECT_ROOT / "scripts" / "run_app_backend.py"),
        ],
        run_local_app.PROJECT_ROOT,
    )
    frontend = run_local_app._start_process(
        "Frontend",
        [run_local_app._npm_command(), "run", "dev"],
        run_local_app.FRONTEND_ROOT,
    )

    assert backend.name == "Backend"
    assert frontend.name == "Frontend"
    assert calls[0][0][0] == run_local_app.sys.executable
    assert calls[0][1] == run_local_app.PROJECT_ROOT
    assert calls[1][0] == [run_local_app._npm_command(), "run", "dev"]
    assert calls[1][1] == run_local_app.FRONTEND_ROOT
    expected_flags = (
        run_local_app.subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    assert calls[0][2] == expected_flags
    assert calls[1][2] == expected_flags


def test_launcher_dependency_check_accepts_current_checkout(monkeypatch):
    monkeypatch.setattr(run_local_app.shutil, "which", lambda command: command)

    assert run_local_app._dependency_error() is None


def test_double_click_entrypoint_calls_python_launcher():
    entrypoint = Path("start_local_app.cmd").read_text(encoding="utf-8")

    assert "python scripts\\run_local_app.py" in entrypoint
    assert "cd /d" in entrypoint
    assert "0.0.0.0" not in entrypoint
