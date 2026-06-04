from pathlib import Path

from fastapi.testclient import TestClient

from app_backend.main import ALLOWED_CORS_ORIGINS, app
from run_app_backend import HOST


def test_cors_allows_only_local_vite_origins():
    assert "*" not in ALLOWED_CORS_ORIGINS
    assert set(ALLOWED_CORS_ORIGINS) == {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }


def test_status_cors_preflight_uses_strict_local_origin():
    response = TestClient(app).options(
        "/api/status",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert "POST" in response.headers["access-control-allow-methods"]


def test_backend_runner_binds_localhost_only():
    assert HOST == "127.0.0.1"
    runner = Path("scripts/run_app_backend.py").read_text(encoding="utf-8")
    assert "0.0.0.0" not in runner
