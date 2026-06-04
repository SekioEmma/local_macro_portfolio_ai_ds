from __future__ import annotations

import sqlite3
from pathlib import Path

from app_backend.schemas.responses import (
    AppSettingsResponse,
    CreateFavoriteAnswerRequest,
    CreateRefreshRunRequest,
    FavoriteAnswer,
    RefreshRun,
    StorageStatusResponse,
    UpdateAppSettingsRequest,
)
from app_backend.storage import database, repositories
from app_backend.storage.migrations import get_schema_version
from app_backend.storage.repositories import UnsafeAppStateValueError


DEFAULT_DB_PATH = database.get_default_db_path()


class AppStateInputError(ValueError):
    pass


def storage_status(db_path: Path | None = None) -> StorageStatusResponse:
    path = db_path or DEFAULT_DB_PATH
    existed_before = path.exists()
    try:
        initialized_path = database.initialize_app_db(path)
        with database.connect_app_db(initialized_path) as connection:
            version = get_schema_version(connection)
        return StorageStatusResponse(
            storage_mode="sqlite",
            database_exists=initialized_path.exists(),
            schema_version=version,
            initialized=True,
            error_summary=None,
        )
    except sqlite3.Error:
        return StorageStatusResponse(
            storage_mode="sqlite",
            database_exists=existed_before,
            schema_version=None,
            initialized=False,
            error_summary="app state database is invalid or unavailable",
        )


def get_settings(db_path: Path | None = None) -> AppSettingsResponse:
    try:
        return AppSettingsResponse(
            settings=repositories.get_settings(_path(db_path)),
            updated_at=repositories.get_settings_updated_at(_path(db_path)),
        )
    except sqlite3.Error as exc:
        raise RuntimeError("app settings unavailable") from exc


def update_settings(
    request: UpdateAppSettingsRequest,
    db_path: Path | None = None,
) -> AppSettingsResponse:
    try:
        repositories.update_settings(request.settings, _path(db_path))
        return get_settings(db_path)
    except UnsafeAppStateValueError as exc:
        raise AppStateInputError(str(exc)) from exc
    except ValueError as exc:
        raise AppStateInputError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise RuntimeError("app settings unavailable") from exc


def list_refresh_runs(limit: int = 50, db_path: Path | None = None) -> list[RefreshRun]:
    try:
        return [RefreshRun(**item) for item in repositories.list_refresh_runs(limit, _path(db_path))]
    except sqlite3.Error as exc:
        raise RuntimeError("refresh runs unavailable") from exc


def create_refresh_run(
    request: CreateRefreshRunRequest,
    db_path: Path | None = None,
) -> RefreshRun:
    try:
        item = repositories.create_refresh_run(
            kind=request.kind,
            status=request.status,
            started_at=request.started_at,
            finished_at=request.finished_at,
            summary=request.summary or {},
            error_summary=request.error_summary,
            db_path=_path(db_path),
        )
        return RefreshRun(**item)
    except UnsafeAppStateValueError as exc:
        raise AppStateInputError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise RuntimeError("refresh runs unavailable") from exc


def list_favorites(limit: int = 50, db_path: Path | None = None) -> list[FavoriteAnswer]:
    try:
        return [FavoriteAnswer(**item) for item in repositories.list_favorites(limit, _path(db_path))]
    except sqlite3.Error as exc:
        raise RuntimeError("favorite answers unavailable") from exc


def create_favorite(
    request: CreateFavoriteAnswerRequest,
    db_path: Path | None = None,
) -> FavoriteAnswer:
    try:
        item = repositories.create_favorite(
            title=request.title,
            question=request.question,
            answer=request.answer,
            model=request.model,
            context_snapshot_json=request.context_snapshot or {},
            db_path=_path(db_path),
        )
        return FavoriteAnswer(**item)
    except UnsafeAppStateValueError as exc:
        raise AppStateInputError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise RuntimeError("favorite answers unavailable") from exc


def _path(db_path: Path | None) -> Path:
    return db_path or DEFAULT_DB_PATH
