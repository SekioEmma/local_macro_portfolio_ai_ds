from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


INDEX_GENERATION_FILENAME = "index_generation.json"
INDEX_GENERATION_SCHEMA_VERSION = 1


def build_index_generation_metadata(
    *,
    documents: Iterable[Any],
    mode: str,
    chunk_count: int,
    written_chunk_count: int,
    pruned_document_count: int,
    vector_enabled: bool,
    embedding_service: Any | None,
) -> dict[str, Any]:
    """Build metadata for one governed RAG index generation.

    The payload intentionally contains only identifiers, hashes, counts, and
    embedding compatibility metadata. It must not include raw document text.
    """
    document_rows = [
        {
            "document_id": str(getattr(document, "document_id", "")),
            "cleaned_content_sha256": str(getattr(document, "cleaned_content_sha256", "")),
            "doc_type": str(getattr(document, "doc_type", "")),
            "evidence_tier": str(getattr(document, "evidence_tier", "")),
            "is_official_source": bool(getattr(document, "is_official_source", False)),
        }
        for document in documents
    ]
    document_rows.sort(key=lambda row: row["document_id"])
    source_hash = _sha256_json(document_rows)
    embedding_model = _embedding_model_name(embedding_service) if vector_enabled else None
    embedding_dim = _embedding_dim(embedding_service) if vector_enabled else None
    basis = {
        "schema_version": INDEX_GENERATION_SCHEMA_VERSION,
        "source_hash": source_hash,
        "mode": mode,
        "chunk_count": chunk_count,
        "written_chunk_count": written_chunk_count,
        "pruned_document_count": pruned_document_count,
        "vector_enabled": vector_enabled,
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
        "document_count": len(document_rows),
    }
    generation_id = _sha256_json(basis)
    return {
        **basis,
        "generation_id": generation_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
    }


def index_generation_path(vector_root: Path) -> Path:
    return vector_root / INDEX_GENERATION_FILENAME


def read_index_generation_metadata(vector_root: Path) -> dict[str, Any] | None:
    path = index_generation_path(vector_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != INDEX_GENERATION_SCHEMA_VERSION:
        return None
    if not isinstance(payload.get("generation_id"), str) or not payload["generation_id"]:
        return None
    return payload


def write_index_generation_metadata(vector_root: Path, payload: dict[str, Any]) -> None:
    vector_root.mkdir(parents=True, exist_ok=True)
    target = index_generation_path(vector_root)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)


def _embedding_model_name(embedding_service: Any | None) -> str | None:
    value = getattr(embedding_service, "model_name", None)
    return value if isinstance(value, str) and value.strip() else None


def _embedding_dim(embedding_service: Any | None) -> int | None:
    try:
        value = getattr(embedding_service, "dim", None)
    except Exception:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "INDEX_GENERATION_FILENAME",
    "INDEX_GENERATION_SCHEMA_VERSION",
    "build_index_generation_metadata",
    "index_generation_path",
    "read_index_generation_metadata",
    "write_index_generation_metadata",
]
