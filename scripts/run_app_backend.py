from __future__ import annotations

import socket
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
HOST = "127.0.0.1"
PORT = 8765


def main() -> int:
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))

    if not _port_available(HOST, PORT):
        print(
            f"Port {PORT} is already in use on {HOST}; stop the existing service or choose a free local port.",
            file=sys.stderr,
        )
        return 1

    uvicorn.run(
        "app_backend.main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False,
    )
    return 0


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) != 0


if __name__ == "__main__":
    raise SystemExit(main())
