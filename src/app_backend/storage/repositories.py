from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_backend.storage import database
from app_backend.storage.migrations import DEFAULT_SETTINGS


SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"[A-Z_]*API_KEY", re.IGNORECASE),
)
ALLOWED_SETTINGS = set(DEFAULT_SETTINGS)
MAX_LIMIT = 100


class UnsafeAppStateValueError(ValueError):
    pass


def get_settings(db_path: Path | None = None) -> dict[str, Any]:
    with _connect_initialized(db_path) as connection:
        rows = connection.execute(
            "SELECT key, value_json FROM app_settings ORDER BY key"
        ).fetchall()
    return {row["key"]: json.loads(row["value_json"]) for row in rows}


def get_settings_updated_at(db_path: Path | None = None) -> str | None:
    with _connect_initialized(db_path) as connection:
        row = connection.execute(
            "SELECT MAX(updated_at) AS updated_at FROM app_settings"
        ).fetchone()
    if row is None:
        return None
    return row["updated_at"]


def update_settings(settings: dict[str, Any], db_path: Path | None = None) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise ValueError("settings must be a JSON object")
    unknown_keys = set(settings) - ALLOWED_SETTINGS
    if unknown_keys:
        raise ValueError(f"Unsupported settings keys: {', '.join(sorted(unknown_keys))}")
    _assert_safe(settings)
    now = _utc_now()
    with _connect_initialized(db_path) as connection:
        for key, value in settings.items():
            connection.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=True), now),
            )
        connection.commit()
    return get_settings(db_path)


def list_refresh_runs(limit: int = 50, db_path: Path | None = None) -> list[dict[str, Any]]:
    with _connect_initialized(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, kind, status, started_at, finished_at, summary_json,
                   error_summary, created_at
            FROM refresh_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (_bounded_limit(limit),),
        ).fetchall()
    return [_refresh_run_from_row(row) for row in rows]


def create_refresh_run(
    kind: str,
    status: str,
    started_at: str,
    finished_at: str | None = None,
    summary: dict[str, Any] | None = None,
    error_summary: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    payload = {
        "kind": kind,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "summary": summary or {},
        "error_summary": error_summary,
    }
    _assert_safe(payload)
    created_at = _utc_now()
    with _connect_initialized(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO refresh_runs (
                kind, status, started_at, finished_at, summary_json,
                error_summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(kind),
                str(status),
                str(started_at),
                finished_at,
                json.dumps(summary or {}, ensure_ascii=True),
                error_summary,
                created_at,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, kind, status, started_at, finished_at, summary_json,
                   error_summary, created_at
            FROM refresh_runs
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return _refresh_run_from_row(row)


def list_favorites(limit: int = 50, db_path: Path | None = None) -> list[dict[str, Any]]:
    with _connect_initialized(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, title, question, answer, model, context_snapshot_json, created_at
            FROM favorite_answers
            ORDER BY id DESC
            LIMIT ?
            """,
            (_bounded_limit(limit),),
        ).fetchall()
    return [_favorite_from_row(row) for row in rows]


def create_favorite(
    title: str | None,
    question: str,
    answer: str,
    model: str | None = None,
    context_snapshot_json: dict[str, Any] | None = None,
    created_at: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    context_snapshot = context_snapshot_json or {}
    payload = {
        "title": title,
        "question": question,
        "answer": answer,
        "model": model,
        "context_snapshot": context_snapshot,
    }
    _assert_safe(payload)
    created = created_at or _utc_now()
    with _connect_initialized(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO favorite_answers (
                title, question, answer, model, context_snapshot_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                str(question),
                str(answer),
                model,
                json.dumps(context_snapshot, ensure_ascii=True),
                created,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, title, question, answer, model, context_snapshot_json, created_at
            FROM favorite_answers
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return _favorite_from_row(row)


def _connect_initialized(db_path: Path | None = None) -> sqlite3.Connection:
    path = database.initialize_app_db(db_path)
    return database.connect_app_db(path)


def _refresh_run_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "summary": json.loads(row["summary_json"] or "{}"),
        "error_summary": row["error_summary"],
        "created_at": row["created_at"],
    }


def _favorite_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "question": row["question"],
        "answer": row["answer"],
        "model": row["model"],
        "context_snapshot": json.loads(row["context_snapshot_json"] or "{}"),
        "created_at": row["created_at"],
    }


def _assert_safe(value: Any) -> None:
    if _contains_secret(value):
        raise UnsafeAppStateValueError("app state input contains secret-like content")


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_secret(key) or _contains_secret(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SECRET_PATTERNS)
    return False


def _bounded_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return 50
    return max(1, min(parsed, MAX_LIMIT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
