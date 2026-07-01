from __future__ import annotations

import pytest

from app_backend.services.local_rag_runtime_factory import (
    build_local_rag_runtime,
    invalidate_local_rag_runtime_cache,
)
from app_backend.services.rag_index_generation import (
    CHUNKING_VERSION,
    INDEX_GENERATION_SCHEMA_VERSION,
    RAGIndexCompatibilityError,
    write_index_generation_metadata,
)
from llm.chunk_text_store import ChunkTextStore, StoredChunk


class _StubBM25:
    def __init__(self, corpus: list[list[str]]) -> None:
        self.corpus = corpus

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        return [float(len(set(query_tokens) & set(tokens))) for tokens in self.corpus]


def _seed_one_chunk(vector_dir):
    store = ChunkTextStore(vector_dir / "chunks.sqlite")
    store.upsert_chunk(
        StoredChunk("public", 0, "federal reserve policy", "Public", "policy_doc", "federalreserve.gov")
    )
    _write_generation(vector_dir, generation_id="generation-one")
    return store


def _write_generation(
    vector_dir,
    *,
    generation_id: str = "generation-one",
    chunking_version: str = CHUNKING_VERSION,
    vector_enabled: bool = False,
    embedding_model: str | None = None,
    embedding_dim: int | None = None,
):
    payload = {
        "schema_version": INDEX_GENERATION_SCHEMA_VERSION,
        "generation_id": generation_id,
        "chunking_version": chunking_version,
        "vector_enabled": vector_enabled,
    }
    if embedding_model is not None:
        payload["embedding_model"] = embedding_model
    if embedding_dim is not None:
        payload["embedding_dim"] = embedding_dim
    write_index_generation_metadata(
        vector_dir,
        payload,
    )


def test_runtime_factory_builds_bm25_from_external_allowed_chunks(tmp_path):
    vector_dir = tmp_path / "vector_store"
    store = ChunkTextStore(vector_dir / "chunks.sqlite")
    store.upsert_chunk(
        StoredChunk("public", 0, "federal reserve policy", "Public", "policy_doc", "federalreserve.gov")
    )
    store.upsert_chunk(
        StoredChunk(
            "private",
            0,
            "private memo",
            "Private",
            "research_report",
            "example.com",
            external_llm_context_allowed=False,
        )
    )
    _write_generation(vector_dir)

    runtime = build_local_rag_runtime(vector_dir, _bm25_factory=_StubBM25)

    assert runtime.searchable_chunk_count == 1
    assert runtime.bm25_index.size == 1
    assert runtime.bm25_index.query("private") == []
    assert runtime.bm25_index.query("federal")[0].doc_id == "public"


def test_runtime_factory_caches_per_vector_root(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    invalidate_local_rag_runtime_cache()

    first = build_local_rag_runtime(vector_dir)
    second = build_local_rag_runtime(vector_dir)

    assert first is second  # same cached instance — no rebuild
    invalidate_local_rag_runtime_cache(vector_dir)


def test_runtime_factory_cache_key_includes_index_generation_id(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    invalidate_local_rag_runtime_cache()

    first = build_local_rag_runtime(vector_dir)
    _write_generation(vector_dir, generation_id="generation-two")
    second = build_local_rag_runtime(vector_dir)

    assert first is not second
    assert second.index_generation is not None
    assert second.index_generation["generation_id"] == "generation-two"
    invalidate_local_rag_runtime_cache(vector_dir)


def test_runtime_factory_bm25_factory_override_bypasses_cache(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    invalidate_local_rag_runtime_cache()

    cached = build_local_rag_runtime(vector_dir)
    forced = build_local_rag_runtime(vector_dir, _bm25_factory=_StubBM25)
    cached_after = build_local_rag_runtime(vector_dir)

    # The stub-factory build does not enter the cache, and does not displace
    # the cached non-stub build.
    assert forced is not cached
    assert cached_after is cached
    invalidate_local_rag_runtime_cache(vector_dir)


def test_runtime_factory_use_cache_false_bypasses_cache(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    invalidate_local_rag_runtime_cache()

    cached = build_local_rag_runtime(vector_dir)
    fresh = build_local_rag_runtime(vector_dir, use_cache=False)
    cached_after = build_local_rag_runtime(vector_dir)

    assert fresh is not cached
    assert cached_after is cached  # use_cache=False does not pollute the cache
    invalidate_local_rag_runtime_cache(vector_dir)


def test_invalidate_drops_cached_entry(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    invalidate_local_rag_runtime_cache()

    first = build_local_rag_runtime(vector_dir)
    invalidate_local_rag_runtime_cache(vector_dir)
    second = build_local_rag_runtime(vector_dir)

    assert first is not second  # cache cleared, rebuild produced a fresh instance
    invalidate_local_rag_runtime_cache(vector_dir)


def test_invalidate_all_drops_every_entry(tmp_path):
    vector_dir_a = tmp_path / "va"
    vector_dir_b = tmp_path / "vb"
    _seed_one_chunk(vector_dir_a)
    _seed_one_chunk(vector_dir_b)
    invalidate_local_rag_runtime_cache()

    a1 = build_local_rag_runtime(vector_dir_a)
    b1 = build_local_rag_runtime(vector_dir_b)
    invalidate_local_rag_runtime_cache()  # no arg -> clear everything
    a2 = build_local_rag_runtime(vector_dir_a)
    b2 = build_local_rag_runtime(vector_dir_b)

    assert a1 is not a2
    assert b1 is not b2
    invalidate_local_rag_runtime_cache()


def test_runtime_factory_rejects_missing_index_generation_for_nonempty_chunks(tmp_path):
    vector_dir = tmp_path / "vector_store"
    store = ChunkTextStore(vector_dir / "chunks.sqlite")
    store.upsert_chunk(
        StoredChunk("public", 0, "federal reserve policy", "Public", "policy_doc", "federalreserve.gov")
    )

    with pytest.raises(RAGIndexCompatibilityError, match="index_generation_missing_or_invalid"):
        build_local_rag_runtime(vector_dir, _bm25_factory=_StubBM25)


def test_runtime_factory_rejects_chunking_version_mismatch(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    _write_generation(vector_dir, chunking_version="old_chunking")

    with pytest.raises(RAGIndexCompatibilityError, match="chunking_version_mismatch"):
        build_local_rag_runtime(vector_dir, _bm25_factory=_StubBM25)


def test_runtime_factory_rejects_embedding_model_mismatch(tmp_path):
    vector_dir = tmp_path / "vector_store"
    _seed_one_chunk(vector_dir)
    _write_generation(
        vector_dir,
        vector_enabled=True,
        embedding_model="other-model",
        embedding_dim=1024,
    )

    with pytest.raises(RAGIndexCompatibilityError, match="embedding_model_mismatch"):
        build_local_rag_runtime(vector_dir, _bm25_factory=_StubBM25)
