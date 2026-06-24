from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from app_backend.services.knowledge_base_contracts import (
    KnowledgeBaseAdmissionError,
    KnowledgeDocumentInput,
    admit_document,
    canonicalize_document_url,
)


_DEFAULT_DB_PATH = Path("data/knowledge_base.sqlite")
_DEFAULT_RAW_ROOT = Path("data/knowledge_base/raw")
_SCHEMA_PATH = Path(__file__).with_name("knowledge_base_schema.sql")


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    id: int
    url: str
    title: str
    source_domain: str
    doc_type: str
    fetched_at: str
    content_sha256: str
    is_stale: bool
    stale_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class KnowledgeIngestResult:
    status: str
    document: KnowledgeDocumentRecord
    created: bool
    updated: bool


@dataclass(frozen=True)
class KnowledgeMutationResult:
    status: str
    document: KnowledgeDocumentRecord | None = None


class KnowledgeBaseService:
    def __init__(
        self,
        db_path: Path = _DEFAULT_DB_PATH,
        raw_root: Path = _DEFAULT_RAW_ROOT,
    ) -> None:
        self._db_path = db_path
        self._raw_root = raw_root

    def ingest_document(self, document: KnowledgeDocumentInput) -> KnowledgeIngestResult:
        admitted = admit_document(document)
        raw_relative_path = f"raw/{admitted.content_sha256}.txt"
        raw_file = self._safe_raw_file(admitted.content_sha256)

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_root.mkdir(parents=True, exist_ok=True)
        if not raw_file.exists():
            raw_file.write_text(admitted.raw_text, encoding="utf-8")

        now = _utc_now()
        with self._connect_existing_or_new() as connection:
            self._initialize_schema(connection)
            existing = self._fetch_record_by_url(connection, admitted.canonical_url)
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO documents (
                        url, title, source_domain, doc_type, fetched_at, content_sha256,
                        raw_text_path, is_stale, stale_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                    """,
                    (
                        admitted.canonical_url,
                        admitted.title,
                        admitted.source_domain,
                        admitted.doc_type.value,
                        admitted.fetched_at,
                        admitted.content_sha256,
                        raw_relative_path,
                        now,
                        now,
                    ),
                )
                record = self._fetch_record_by_url(connection, admitted.canonical_url)
                if record is None:
                    raise RuntimeError("knowledge_base_write_failed")
                return KnowledgeIngestResult(
                    status="created",
                    document=record,
                    created=True,
                    updated=False,
                )

            if existing.content_sha256 != admitted.content_sha256:
                connection.execute(
                    "DELETE FROM document_chunks WHERE doc_id = ?",
                    (existing.id,),
                )
            connection.execute(
                """
                UPDATE documents
                SET title = ?,
                    source_domain = ?,
                    doc_type = ?,
                    fetched_at = ?,
                    content_sha256 = ?,
                    raw_text_path = ?,
                    is_stale = 0,
                    stale_at = NULL,
                    updated_at = ?
                WHERE url = ?
                """,
                (
                    admitted.title,
                    admitted.source_domain,
                    admitted.doc_type.value,
                    admitted.fetched_at,
                    admitted.content_sha256,
                    raw_relative_path,
                    now,
                    admitted.canonical_url,
                ),
            )
            record = self._fetch_record_by_url(connection, admitted.canonical_url)
            if record is None:
                raise RuntimeError("knowledge_base_write_failed")
            return KnowledgeIngestResult(
                status="updated",
                document=record,
                created=False,
                updated=True,
            )

    def lookup_by_url(self, url: str) -> KnowledgeDocumentRecord | None:
        canonical_url, _source_domain = canonicalize_document_url(url)
        if not self._db_path.exists():
            return None
        with self._connect_existing() as connection:
            return self._fetch_record_by_url(connection, canonical_url)

    def mark_stale(self, url: str) -> KnowledgeMutationResult:
        canonical_url, _source_domain = canonicalize_document_url(url)
        if not self._db_path.exists():
            return KnowledgeMutationResult(status="not_found")
        stale_at = _utc_now()
        with self._connect_existing() as connection:
            record = self._fetch_record_by_url(connection, canonical_url)
            if record is None:
                return KnowledgeMutationResult(status="not_found")
            connection.execute(
                """
                UPDATE documents
                SET is_stale = 1,
                    stale_at = ?,
                    updated_at = ?
                WHERE url = ?
                """,
                (stale_at, stale_at, canonical_url),
            )
            updated = self._fetch_record_by_url(connection, canonical_url)
            return KnowledgeMutationResult(status="stale", document=updated)

    def list_recent(
        self,
        limit: int = 20,
        include_stale: bool = False,
    ) -> list[KnowledgeDocumentRecord]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise KnowledgeBaseAdmissionError("invalid_limit")
        if not self._db_path.exists():
            return []
        stale_clause = "" if include_stale else "WHERE is_stale = 0"
        with self._connect_existing() as connection:
            rows = connection.execute(
                f"""
                SELECT id, url, title, source_domain, doc_type, fetched_at,
                       content_sha256, is_stale, stale_at, created_at, updated_at
                FROM documents
                {stale_clause}
                ORDER BY fetched_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_record_from_row(row) for row in rows]

    def _safe_raw_file(self, content_sha256: str) -> Path:
        raw_file = self._raw_root / f"{content_sha256}.txt"
        raw_root = self._raw_root.resolve(strict=False)
        resolved_file = raw_file.resolve(strict=False)
        if raw_root != resolved_file.parent:
            raise KnowledgeBaseAdmissionError("invalid_raw_text")
        return raw_file

    def _connect_existing_or_new(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _connect_existing(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._db_path}?mode=rw", uri=True)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))

    def _fetch_record_by_url(
        self,
        connection: sqlite3.Connection,
        canonical_url: str,
    ) -> KnowledgeDocumentRecord | None:
        row = connection.execute(
            """
            SELECT id, url, title, source_domain, doc_type, fetched_at,
                   content_sha256, is_stale, stale_at, created_at, updated_at
            FROM documents
            WHERE url = ?
            """,
            (canonical_url,),
        ).fetchone()
        return _record_from_row(row) if row is not None else None


def build_default_knowledge_base_service() -> KnowledgeBaseService:
    return KnowledgeBaseService()


def _record_from_row(row: Any) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        id=int(row[0]),
        url=str(row[1]),
        title=str(row[2]),
        source_domain=str(row[3]),
        doc_type=str(row[4]),
        fetched_at=str(row[5]),
        content_sha256=str(row[6]),
        is_stale=bool(row[7]),
        stale_at=str(row[8]) if row[8] is not None else None,
        created_at=str(row[9]),
        updated_at=str(row[10]),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "KnowledgeBaseService",
    "KnowledgeDocumentRecord",
    "KnowledgeIngestResult",
    "KnowledgeMutationResult",
    "build_default_knowledge_base_service",
]
