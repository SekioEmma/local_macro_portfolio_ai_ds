import json
import socket

import pytest


TestClient = pytest.importorskip("fastapi.testclient").TestClient
app = pytest.importorskip("app_backend.main").app


API_KEY_ENV_NAMES = [
    "DEEPSEEK_API_KEY",
    "FRED_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "BEA_API_KEY",
    "TAVILY_API_KEY",
]


def test_status_endpoint_returns_safe_minimal_status(monkeypatch):
    for env_name in API_KEY_ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)

    def _block_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in /api/status tests.")

    monkeypatch.setattr(socket, "create_connection", _block_network)

    client = TestClient(app)
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "local_macro_portfolio_ai_ds"
    assert data["mode"] == "local_dev"
    assert data["storage_mode"] == "file_based"
    assert set(data["api_keys_configured"]) == {
        "deepseek",
        "fred",
        "alpha_vantage",
        "bea",
        "tavily",
    }
    assert all(value is False for value in data["api_keys_configured"].values())
    assert {
        "api_keys_env_only",
        "holdings_not_returned",
        "data_private_not_served",
        "outputs_not_served_raw",
        "local_backend_only",
    }.issubset(set(data["privacy_boundaries"]))
    assert data["project_root_exists"] is True

    body = json.dumps(data, sort_keys=True)
    assert "G:\\local_macro_portfolio_ai\\local_macro_portfolio_ai_ds" not in body
    assert "current_holdings.csv" not in body
    assert "data/private" not in body
    assert "outputs/reports" not in body
    assert "outputs/analyst_memos" not in body
