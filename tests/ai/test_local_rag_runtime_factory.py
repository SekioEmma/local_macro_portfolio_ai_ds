from __future__ import annotations

from app_backend.services.local_rag_runtime_factory import build_local_rag_runtime
from llm.chunk_text_store import ChunkTextStore, StoredChunk


class _StubBM25:
    def __init__(self, corpus: list[list[str]]) -> None:
        self.corpus = corpus

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        return [float(len(set(query_tokens) & set(tokens))) for tokens in self.corpus]


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

