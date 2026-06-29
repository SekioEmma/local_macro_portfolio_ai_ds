from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from app_backend.services.rag_retrieval_service import RAGRetrievalService
from llm.bm25_index import BM25Index
from llm.chunk_text_store import ChunkTextStore
from llm.embedding_service import EmbeddingService
from llm.vector_store import VectorStore


DEFAULT_VECTOR_ROOT = Path(__file__).resolve().parents[3] / "data" / "vector_store"
DEFAULT_VECTOR_DIR = DEFAULT_VECTOR_ROOT


@dataclass(frozen=True)
class LocalRAGRuntime:
    chunk_store: ChunkTextStore
    vector_store: VectorStore
    bm25_index: BM25Index
    embedding_service: EmbeddingService
    retrieval_service: RAGRetrievalService
    searchable_chunk_count: int


# Process-local cache of fully built runtimes keyed by the resolved vector
# root. Building a runtime reads the full chunk store and re-tokenizes the
# corpus for BM25, which is O(corpus) — hot tool-call paths must not repeat
# that on every invocation. The cache is intentionally invalidated only by
# explicit `invalidate_local_rag_runtime_cache()` calls (e.g. after an
# ingest or in tests); there is no implicit TTL.
_RUNTIME_CACHE: dict[Path, LocalRAGRuntime] = {}
_RUNTIME_CACHE_LOCK = Lock()


def build_local_rag_runtime(
    vector_root: Path = DEFAULT_VECTOR_ROOT,
    *,
    _bm25_factory: Any = None,
    offline_only: bool = True,
    use_cache: bool = True,
) -> LocalRAGRuntime:
    """Return a LocalRAGRuntime for the given vector root.

    By default the runtime is cached per resolved vector_root for the lifetime
    of the process. Pass ``use_cache=False`` to force a fresh build (the
    result is not stored in the cache), or call
    ``invalidate_local_rag_runtime_cache()`` to drop the cached entry after a
    corpus change. ``_bm25_factory`` overrides bypass the cache because they
    are test-only and never used in the request path.
    """
    resolved = vector_root.resolve()
    if use_cache and _bm25_factory is None:
        with _RUNTIME_CACHE_LOCK:
            cached = _RUNTIME_CACHE.get(resolved)
            if cached is not None:
                return cached

    runtime = _build_runtime_uncached(
        resolved,
        bm25_factory=_bm25_factory,
        offline_only=offline_only,
    )

    if use_cache and _bm25_factory is None:
        with _RUNTIME_CACHE_LOCK:
            _RUNTIME_CACHE[resolved] = runtime
    return runtime


def invalidate_local_rag_runtime_cache(vector_root: Path | None = None) -> None:
    """Drop one or all cached runtimes.

    Call after an ingest that changed the chunk store / vector store, or in
    tests that need a fresh build. ``None`` clears every cached entry.
    """
    with _RUNTIME_CACHE_LOCK:
        if vector_root is None:
            _RUNTIME_CACHE.clear()
            return
        _RUNTIME_CACHE.pop(vector_root.resolve(), None)


def _build_runtime_uncached(
    vector_root: Path,
    *,
    bm25_factory: Any,
    offline_only: bool,
) -> LocalRAGRuntime:
    chunk_store = ChunkTextStore(vector_root / "chunks.sqlite")
    chunks = chunk_store.list_chunks(external_llm_context_allowed=True)

    bm25_index = BM25Index(_bm25_factory=bm25_factory)
    bm25_index.build([(chunk.doc_id, chunk.chunk_index, chunk.text) for chunk in chunks])

    embedding_service = EmbeddingService(offline_only=offline_only)
    vector_store = VectorStore(vector_root / "chroma")
    retrieval_service = RAGRetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        bm25_index=bm25_index,
        raw_text_store=chunk_store,
    )
    return LocalRAGRuntime(
        chunk_store=chunk_store,
        vector_store=vector_store,
        bm25_index=bm25_index,
        embedding_service=embedding_service,
        retrieval_service=retrieval_service,
        searchable_chunk_count=len(chunks),
    )
