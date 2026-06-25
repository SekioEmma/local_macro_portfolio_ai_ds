#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_backend.services.curated_rag_ingest import (  # noqa: E402
    DEFAULT_VECTOR_ROOT,
    build_ingest_plan,
    summarize_plan,
)
from app_backend.services.local_rag_runtime_factory import build_local_rag_runtime  # noqa: E402
from app_backend.services.rag_context_builder import build_rag_context  # noqa: E402
from llm.chunk_text_store import ChunkTextStore  # noqa: E402
from llm.embedding_service import OfflineEmbeddingModelNotAvailable  # noqa: E402


SMOKE_QUERIES = [
    ("federal funds target range June 2026 FOMC statement", "fomc_statement_2026_06_17"),
    ("interest on reserve balances ON RRP SOMA implementation", None),
    ("Summary of Economic Projections unemployment PCE federal funds rate", "fomc_projection_materials"),
    ("Committee policy actions minutes financial conditions", "fomc_minutes"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local governed RAG indexes without network or LLM calls.")
    parser.add_argument("--curated-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vector-root", type=Path, default=DEFAULT_VECTOR_ROOT)
    parser.add_argument("--vector-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        plan = build_ingest_plan(args.curated_root, args.manifest)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    vector_root = (args.vector_dir or args.vector_root).resolve()
    chunk_db = vector_root / "chunks.sqlite"
    chunk_count = _chunk_count(chunk_db)
    local_only_chunk_count = _local_only_chunk_count(chunk_db)
    doc_count = _doc_count(chunk_db)
    chroma_count = _chroma_count(vector_root / "chroma") if chunk_count else 0

    bm25_size = 0
    smoke: list[dict[str, Any]] = []
    context_ok = False
    embedding_status = "not_loaded"
    if plan.accepted_document_count and chunk_count:
        try:
            runtime = build_local_rag_runtime(vector_root, offline_only=True)
            bm25_size = runtime.bm25_index.size
            smoke = _run_smoke(runtime)
            context_ok = any(item["pass_fail"] == "pass" and item["retrieval_mode"] == "context" for item in smoke)
            embedding_status = "offline_model_loaded" if any(
                item["retrieval_mode"] == "vector" and item["pass_fail"] != "skipped" for item in smoke
            ) else "bm25_only_embedding_unavailable"
        except OfflineEmbeddingModelNotAvailable as exc:
            smoke = _skipped_smoke()
            embedding_status = str(exc)
    else:
        smoke = _skipped_smoke()

    payload = {
        "manifest_audit": summarize_plan(plan),
        "eligible_document_count": plan.accepted_document_count,
        "indexed_document_count": doc_count,
        "chunk_store_count": chunk_count,
        "rejected_count_by_reason": dict(sorted(plan.rejected_reasons.items())),
        "external_llm_denied_chunk_count": local_only_chunk_count,
        "context_builder_status": "ok" if context_ok else "skipped_or_empty",
        "offline_embedding_status": embedding_status,
        "stored_document_count": doc_count,
        "stored_chunk_count": chunk_count,
        "chroma_chunk_count": chroma_count,
        "bm25_size": bm25_size,
        "consistency": {
            "eligible_manifest_documents": plan.accepted_document_count,
            "chunk_store_matches_chroma": chunk_count == chroma_count,
            "bm25_matches_searchable_chunks": bm25_size == chunk_count if chunk_count else bm25_size == 0,
            "local_only_chunks": local_only_chunk_count,
            "context_non_empty_under_4000_chars": context_ok,
        },
        "retrieval_smoke": smoke,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if _is_valid(payload) else 1


def _chunk_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    return ChunkTextStore(db_path).count()


def _doc_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    return len(ChunkTextStore(db_path).list_doc_ids())


def _local_only_chunk_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    return len(ChunkTextStore(db_path).list_chunks(external_llm_context_allowed=False))


def _chroma_count(vector_dir: Path) -> int:
    if not vector_dir.exists():
        return 0
    try:
        from llm.vector_store import VectorStore

        return VectorStore(vector_dir).count()
    except (ImportError, sqlite3.DatabaseError, RuntimeError):
        return 0


def _run_smoke(runtime: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    doc_ids = set(runtime.chunk_store.list_doc_ids())
    for query, expected in SMOKE_QUERIES:
        expected = expected if _expected_available(doc_ids, expected) else None
        query_rows = [
            _vector_row(runtime, query, expected),
            _bm25_row(runtime, query, expected),
            _fused_row(runtime, query, expected),
        ]
        fused = runtime.retrieval_service.retrieve(query, top_k=5)
        block = build_rag_context(fused, max_chars=4000)
        query_rows.append(_context_row(query, fused, expected, block))
        rows.extend(query_rows)
    return rows


def _vector_row(runtime: Any, query: str, expected: str | None) -> dict[str, Any]:
    try:
        embedding = runtime.embedding_service.encode_one(query)
        results = runtime.vector_store.query(embedding, top_k=5)
    except ImportError:
        return _empty_row(query, "vector", "skipped")
    return _result_row(runtime, query, "vector", results, expected)


def _bm25_row(runtime: Any, query: str, expected: str | None) -> dict[str, Any]:
    results = runtime.bm25_index.query(query, top_k=5)
    return _result_row(runtime, query, "bm25", results, expected)


def _fused_row(runtime: Any, query: str, expected: str | None) -> dict[str, Any]:
    results = runtime.retrieval_service.retrieve(query, top_k=5)
    if not results:
        return _empty_row(query, "rrf_fused", "fail")
    top = results[0]
    return _format_row(query, "rrf_fused", top.doc_id, top.title, top.doc_type, 1, _matches(top.doc_id, expected))


def _context_row(query: str, fused: list[Any], expected: str | None, block: Any) -> dict[str, Any]:
    if not fused or not block.text or block.char_count > 4000:
        return _empty_row(query, "context", "fail")
    top = fused[0]
    return _format_row(query, "context", top.doc_id, top.title, top.doc_type, 1, _matches(top.doc_id, expected))


def _result_row(runtime: Any, query: str, mode: str, results: list[Any], expected: str | None) -> dict[str, Any]:
    if not results:
        return _empty_row(query, mode, "fail")
    top = results[0]
    raw = runtime.chunk_store.get_chunk(top.doc_id, top.chunk_index)
    if raw is None:
        return _empty_row(query, mode, "fail")
    return _format_row(query, mode, top.doc_id, raw.title, raw.doc_type, 1, _matches(top.doc_id, expected))


def _format_row(
    query: str,
    mode: str,
    doc_id: str | None,
    title: str | None,
    doc_type: str | None,
    rank: int | None,
    passed: bool,
) -> dict[str, Any]:
    return {
        "query": query,
        "top_ranked_document_id": doc_id,
        "title": title,
        "doc_type": doc_type,
        "rank": rank,
        "retrieval_mode": mode,
        "pass_fail": "pass" if passed else "fail",
    }


def _empty_row(query: str, mode: str, status: str) -> dict[str, Any]:
    return {
        "query": query,
        "top_ranked_document_id": None,
        "title": None,
        "doc_type": None,
        "rank": None,
        "retrieval_mode": mode,
        "pass_fail": status,
    }


def _skipped_smoke() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query, _ in SMOKE_QUERIES:
        for mode in ["vector", "bm25", "rrf_fused", "context"]:
            rows.append(_empty_row(query, mode, "skipped"))
    return rows


def _matches(doc_id: str, expected: str | None) -> bool:
    if expected is None:
        return True
    return expected in doc_id


def _expected_available(doc_ids: set[str], expected: str | None) -> bool:
    if expected is None:
        return False
    return any(expected in doc_id for doc_id in doc_ids)


def _is_valid(payload: dict[str, Any]) -> bool:
    consistency = payload["consistency"]
    if payload["manifest_audit"]["accepted_documents"] == 0:
        return consistency["local_only_chunks"] == 0
    return (
        consistency["eligible_manifest_documents"] > 0
        and consistency["bm25_matches_searchable_chunks"]
        and consistency["local_only_chunks"] == 0
        and consistency["context_non_empty_under_4000_chars"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
