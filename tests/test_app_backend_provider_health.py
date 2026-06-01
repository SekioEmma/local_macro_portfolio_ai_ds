import json
import socket

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import provider_service


def test_provider_health_returns_not_run_yet_when_cache_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    monkeypatch.setattr(provider_service, "DEFAULT_HEALTH_PATH", tmp_path / "missing.json")

    response = TestClient(app).get("/api/provider-health")

    assert response.status_code == 200
    data = response.json()
    assert data["generated_at"] is None
    assert data["overall_status"] == "not_run_yet"
    assert data["summary"] == {}
    assert data["checks"] == []
    assert "run_provider_health_check.py --save" in data["next_action"]
    assert data["error_summary"] is None


def test_provider_health_returns_only_compact_cached_fields(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    health_path = tmp_path / "provider_health_check.json"
    health_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "overall_status": "degraded",
                "summary": {"ok": 2, "error": 1},
                "checks": [
                    {
                        "key": "fred_dgs10",
                        "provider": "FRED",
                        "status": "ok",
                        "source": "FRED",
                        "observation_date": "2026-01-01",
                        "value_present": True,
                        "error_type": None,
                        "error_summary": None,
                        "raw_extra": "must_not_leak",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provider_service, "DEFAULT_HEALTH_PATH", health_path)

    response = TestClient(app).get("/api/provider-health")

    assert response.status_code == 200
    data = response.json()
    assert data["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert data["overall_status"] == "degraded"
    assert data["summary"] == {"ok": 2, "error": 1}
    assert data["checks"] == [
        {
            "key": "fred_dgs10",
            "provider": "FRED",
            "status": "ok",
            "source": "FRED",
            "observation_date": "2026-01-01",
            "value_present": True,
            "error_type": None,
            "error_summary": None,
        }
    ]
    assert "raw_extra" not in json.dumps(data, sort_keys=True)
    assert "sk-" not in json.dumps(data, sort_keys=True)


def test_provider_health_truncates_error_summary(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    health_path = tmp_path / "provider_health_check.json"
    health_path.write_text(
        json.dumps(
            {
                "overall_status": "error",
                "checks": [
                    {
                        "key": "alpha_vantage_gold",
                        "provider": "Alpha Vantage",
                        "status": "error",
                        "error_summary": "x" * 250,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provider_service, "DEFAULT_HEALTH_PATH", health_path)

    response = TestClient(app).get("/api/provider-health")

    assert response.status_code == 200
    error_summary = response.json()["checks"][0]["error_summary"]
    assert len(error_summary) <= 200


def test_provider_health_handles_invalid_cache(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    health_path = tmp_path / "provider_health_check.json"
    health_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(provider_service, "DEFAULT_HEALTH_PATH", health_path)

    response = TestClient(app).get("/api/provider-health")

    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "error"
    assert data["summary"] == {}
    assert data["checks"] == []
    assert data["error_summary"] == "provider health cache is invalid or unreadable"
    assert "run_provider_health_check.py --save" in data["next_action"]


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in provider-health tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
