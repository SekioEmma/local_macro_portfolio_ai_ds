from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


CURRENT_SCHEMA_VERSION = 1
DEFAULT_SETTINGS: dict[str, Any] = {
    "ui_language": "zh-CN",
    "default_context_mode": "full",
    "search_enabled_by_default": False,
    "save_chat_by_default": False,
    "show_cost_detail": "details_only",
}


def run_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            summary_json TEXT NOT NULL DEFAULT '{}',
            error_summary TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS favorite_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            model TEXT,
            context_snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    _insert_default_settings(connection)
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, applied_at)
        VALUES (?, ?)
        """,
        (CURRENT_SCHEMA_VERSION, _utc_now()),
    )
    connection.commit()


def get_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    if row is None or row["version"] is None:
        return 0
    return int(row["version"])


def _insert_default_settings(connection: sqlite3.Connection) -> None:
    now = _utc_now()
    for key, value in DEFAULT_SETTINGS.items():
        connection.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(value, ensure_ascii=True), now),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
