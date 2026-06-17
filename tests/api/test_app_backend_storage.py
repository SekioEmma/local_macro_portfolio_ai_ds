import socket

import pytest
from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import storage_service
from app_backend.storage import database, repositories
from app_backend.storage.migrations import CURRENT_SCHEMA_VERSION, get_schema_version


def test_initialize_app_db_is_idempotent(tmp_path):
    db_path = tmp_path / "app_state.sqlite3"

    database.initialize_app_db(db_path)
    database.initialize_app_db(db_path)

    with database.connect_app_db(db_path) as connection:
        assert get_schema_version(connection) == CURRENT_SCHEMA_VERSION
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {
        "schema_migrations",
        "app_settings",
        "refresh_runs",
        "favorite_answers",
    }.issubset(tables)


def test_default_settings_exist_and_update_safely(tmp_path):
    db_path = tmp_path / "app_state.sqlite3"

    settings = repositories.get_settings(db_path)
    assert settings["ui_language"] == "zh-CN"
    assert settings["search_enabled_by_default"] is False

    updated = repositories.update_settings(
        {
            "default_context_mode": "sanitized",
            "show_cost_detail": "hidden",
        },
        db_path,
    )

    assert updated["default_context_mode"] == "sanitized"
    assert updated["show_cost_detail"] == "hidden"


def test_unknown_setting_key_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        repositories.update_settings({"raw_prompt": "do not store"}, tmp_path / "app.sqlite3")


def test_refresh_runs_create_and_list(tmp_path):
    db_path = tmp_path / "app_state.sqlite3"

    created = repositories.create_refresh_run(
        kind="manual_placeholder",
        status="ok",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        summary={"source": "fake sanitized summary"},
        db_path=db_path,
    )
    rows = repositories.list_refresh_runs(db_path=db_path)

    assert created["id"] == rows[0]["id"]
    assert rows[0]["summary"] == {"source": "fake sanitized summary"}


def test_favorites_create_and_list_sanitized_placeholder(tmp_path):
    db_path = tmp_path / "app_state.sqlite3"

    created = repositories.create_favorite(
        title="placeholder",
        question="fake sanitized question",
        answer="fake sanitized answer",
        model="mock",
        context_snapshot_json={"mode": "fake"},
        db_path=db_path,
    )
    rows = repositories.list_favorites(db_path=db_path)

    assert created["id"] == rows[0]["id"]
    assert rows[0]["context_snapshot"] == {"mode": "fake"}


def test_favorite_rejects_secret_like_content(tmp_path):
    fake_secret = "sk-" + ("a" * 26)
    with pytest.raises(repositories.UnsafeAppStateValueError):
        repositories.create_favorite(
            title="bad",
            question="fake",
            answer="contains DEEPSEEK_API_KEY",
            context_snapshot_json={"token": fake_secret},
            db_path=tmp_path / "app_state.sqlite3",
        )


def test_storage_api_uses_tmp_db_and_hides_path(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "app_state.sqlite3"
    monkeypatch.setattr(storage_service, "DEFAULT_DB_PATH", db_path)

    client = TestClient(app)
    response = client.get("/api/app/storage")

    assert response.status_code == 200
    data = response.json()
    assert data["storage_mode"] == "sqlite"
    assert data["database_exists"] is True
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION
    assert data["initialized"] is True
    assert str(tmp_path) not in response.text
    assert db_path.exists()


def test_settings_api_updates_allowed_keys(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    monkeypatch.setattr(storage_service, "DEFAULT_DB_PATH", tmp_path / "app.sqlite3")

    client = TestClient(app)
    response = client.put(
        "/api/app/settings",
        json={"settings": {"default_context_mode": "sanitized"}},
    )

    assert response.status_code == 200
    assert response.json()["settings"]["default_context_mode"] == "sanitized"


def test_app_state_api_rejects_secret_like_favorite(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    monkeypatch.setattr(storage_service, "DEFAULT_DB_PATH", tmp_path / "app.sqlite3")
    fake_secret = "sk-" + ("a" * 26)

    response = TestClient(app).post(
        "/api/app/favorites",
        json={
            "question": "fake question",
            "answer": fake_secret,
            "context_snapshot": {},
        },
    )

    assert response.status_code == 400
    assert "secret-like" in response.json()["detail"]


def test_refresh_and_favorites_api_round_trip(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    monkeypatch.setattr(storage_service, "DEFAULT_DB_PATH", tmp_path / "app.sqlite3")
    client = TestClient(app)

    refresh = client.post(
        "/api/app/refresh-runs",
        json={
            "kind": "manual_placeholder",
            "status": "ok",
            "started_at": "2026-01-01T00:00:00+00:00",
            "summary": {"mode": "fake"},
        },
    )
    favorite = client.post(
        "/api/app/favorites",
        json={
            "title": "placeholder",
            "question": "fake sanitized question",
            "answer": "fake sanitized answer",
            "model": "mock",
            "context_snapshot": {"mode": "fake"},
        },
    )

    assert refresh.status_code == 200
    assert favorite.status_code == 200
    assert client.get("/api/app/refresh-runs").json()[0]["summary"] == {"mode": "fake"}
    assert client.get("/api/app/favorites").json()[0]["context_snapshot"] == {"mode": "fake"}


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in storage tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
