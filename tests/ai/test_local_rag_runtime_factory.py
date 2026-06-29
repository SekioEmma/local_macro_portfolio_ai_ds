from __future__ import annotations

from app_backend.services.local_rag_runtime_factory import (
    build_local_rag_runtime,
    invalidate_local_rag_runtime_cache,
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
    return store


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
