from __future__ import annotations

import sqlite3
from pathlib import Path

from app_backend.storage.migrations import run_migrations


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "app_state" / "app_state.sqlite3"


def get_default_db_path() -> Path:
    return DEFAULT_DB_PATH


def connect_app_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_default_db_path()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_app_db(db_path: Path | None = None) -> Path:
    path = db_path or get_default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect_app_db(path) as connection:
        run_migrations(connection)
    return path
