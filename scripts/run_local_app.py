from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "app_frontend"
HOST = "127.0.0.1"
BACKEND_PORT = 8765
FRONTEND_PORT = 5173
BACKEND_STATUS_URL = f"http://{HOST}:{BACKEND_PORT}/api/status"
FRONTEND_URL = f"http://{HOST}:{FRONTEND_PORT}"
DEFAULT_STARTUP_TIMEOUT_SECONDS = 90.0


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dependency_error = _dependency_error()
    if dependency_error:
        print(dependency_error, file=sys.stderr)
        return 1

    managed: list[ManagedProcess] = []
    try:
        backend_running = _url_ready(BACKEND_STATUS_URL)
        frontend_running = _url_ready(FRONTEND_URL)

        if not backend_running:
            if not _port_available(HOST, BACKEND_PORT):
                return _port_conflict("Backend", BACKEND_PORT, BACKEND_STATUS_URL)
            managed.append(
                _start_process(
                    "Backend",
                    [sys.executable, str(PROJECT_ROOT / "scripts" / "run_app_backend.py")],
                    PROJECT_ROOT,
                )
            )
        else:
            print(f"[Backend] Reusing service at {BACKEND_STATUS_URL}")

        if not frontend_running:
            if not _port_available(HOST, FRONTEND_PORT):
                return _port_conflict("Frontend", FRONTEND_PORT, FRONTEND_URL)
            managed.append(
                _start_process(
                    "Frontend",
                    [_npm_command(), "run", "dev"],
                    FRONTEND_ROOT,
                )
            )
        else:
            print(f"[Frontend] Reusing service at {FRONTEND_URL}")

        _wait_for_url(
            "Backend",
            BACKEND_STATUS_URL,
            managed,
            timeout_seconds=args.timeout,
        )
        _wait_for_url(
            "Frontend",
            FRONTEND_URL,
            managed,
            timeout_seconds=args.timeout,
        )

        print()
        print("Local Macro Portfolio AI is ready.")
        print(f"Frontend: {FRONTEND_URL}")
        print(f"Backend:  {BACKEND_STATUS_URL}")
        if not args.no_browser:
            webbrowser.open(FRONTEND_URL)

        if not managed:
            return 0

        print("Press Ctrl+C to stop the services started by this launcher.")
        return _monitor_processes(managed)
    except KeyboardInterrupt:
        print("\nStopping local services...")
        return 0
    except RuntimeError as exc:
        print(f"\nStartup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        _stop_processes(managed)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the local FastAPI backend and Vite frontend together."
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start services without opening the frontend in the default browser.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_STARTUP_TIMEOUT_SECONDS,
        help="Seconds to wait for each local service to become ready.",
    )
    return parser.parse_args(argv)


def _dependency_error() -> str | None:
    if not FRONTEND_ROOT.is_dir():
        return f"Frontend directory is missing: {FRONTEND_ROOT}"
    if not (FRONTEND_ROOT / "package.json").is_file():
        return f"Frontend package.json is missing: {FRONTEND_ROOT / 'package.json'}"
    if not (FRONTEND_ROOT / "node_modules").is_dir():
        return (
            "Frontend dependencies are not installed. Run "
            "'cd app_frontend; npm install' once, then start the launcher again."
        )
    if shutil.which(_npm_command()) is None:
        return "npm was not found on PATH. Install Node.js/npm and try again."
    return None


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _start_process(name: str, command: list[str], cwd: Path) -> ManagedProcess:
    print(f"[{name}] Starting: {' '.join(command)}")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        command,
        cwd=cwd,
        creationflags=creationflags,
    )
    return ManagedProcess(name=name, process=process)


def _wait_for_url(
    name: str,
    url: str,
    managed: list[ManagedProcess],
    *,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _url_ready(url):
            print(f"[{name}] Ready: {url}")
            return
        exited = _exited_process(managed)
        if exited is not None:
            raise RuntimeError(
                f"{exited.name} exited before startup completed "
                f"(exit code {exited.process.returncode})."
            )
        time.sleep(0.25)
    raise RuntimeError(f"{name} did not become ready within {timeout_seconds:g} seconds.")


def _url_ready(url: str, timeout_seconds: float = 1.0) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) != 0


def _port_conflict(name: str, port: int, expected_url: str) -> int:
    print(
        f"{name} port {HOST}:{port} is already in use, but {expected_url} "
        "did not respond as the expected service.",
        file=sys.stderr,
    )
    return 1


def _monitor_processes(managed: list[ManagedProcess]) -> int:
    while True:
        exited = _exited_process(managed)
        if exited is not None:
            print(
                f"{exited.name} stopped unexpectedly "
                f"(exit code {exited.process.returncode}).",
                file=sys.stderr,
            )
            return exited.process.returncode or 1
        time.sleep(0.5)


def _exited_process(managed: list[ManagedProcess]) -> ManagedProcess | None:
    for item in managed:
        if item.process.poll() is not None:
            return item
    return None


def _stop_processes(managed: list[ManagedProcess]) -> None:
    for item in reversed(managed):
        if item.process.poll() is not None:
            continue
        print(f"[{item.name}] Stopping...")
        _stop_process(item.process)


def _stop_process(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
