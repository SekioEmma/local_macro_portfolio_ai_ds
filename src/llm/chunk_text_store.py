from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    doc_id       TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    text         TEXT NOT NULL,
    title        TEXT NOT NULL,
    doc_type     TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    PRIMARY KEY (doc_id, chunk_index)
);
"""


@dataclass(frozen=True)
class StoredChunk:
    doc_id: str
    chunk_index: int
    text: str
    title: str
    doc_type: str
    source_domain: str


class ChunkTextStore:
    """SQLite-backed store for chunk text and metadata.

    Provides the raw_text_store interface expected by RAGRetrievalService:
      get_chunk(doc_id, chunk_index) -> StoredChunk | None

    Lives at data/vector_store/chunks.sqlite — separate from the knowledge
    base SQLite and the Chroma vector store.  Not committed to git.
    """

    def __init__(self, db_path: Path) -> None:
        if not isinstance(db_path, Path):
            raise TypeError("db_path must be a Path")
        self._db_path = db_path

    def upsert_chunk(self, chunk: StoredChunk) -> None:
        self._validate_chunk(chunk)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                    (doc_id, chunk_index, text, title, doc_type, source_domain)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.doc_id,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.title,
                    chunk.doc_type,
                    chunk.source_domain,
                ),
            )

    def get_chunk(self, doc_id: str, chunk_index: int) -> StoredChunk | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT doc_id, chunk_index, text, title, doc_type, source_domain "
                "FROM chunks WHERE doc_id = ? AND chunk_index = ?",
                (doc_id, chunk_index),
            ).fetchone()
        if row is None:
            return None
        return StoredChunk(*row)

    def delete_doc(self, doc_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            return cur.rowcount

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def list_doc_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT doc_id FROM chunks ORDER BY doc_id"
            ).fetchall()
        return [r[0] for r in rows]

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute(_SCHEMA)
        return conn

    @staticmethod
    def _validate_chunk(chunk: StoredChunk) -> None:
        if not isinstance(chunk, StoredChunk):
            raise TypeError("chunk must be a StoredChunk")
        if not chunk.doc_id.strip():
            raise ValueError("doc_id must be non-empty")
        if isinstance(chunk.chunk_index, bool) or chunk.chunk_index < 0:
            raise ValueError("chunk_index must be non-negative int")
