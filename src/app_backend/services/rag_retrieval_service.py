from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_RRF_K = 60
_DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class RetrievedChunk:
    doc_id: str
    chunk_index: int
    text: str
    rrf_score: float
    title: str
    doc_type: str
    source_domain: str
    external_llm_context_allowed: bool = True


class RAGRetrievalService:
    """Hybrid retrieval: vector cosine + BM25 keyword, fused with RRF.

    Dependencies are injected so tests can run without real models.
    Raw chunk text is passed through; the caller (RAGContextBuilder) is
    responsible for trimming it before it reaches any API response.

    Retrieval-only: no network, no SQLite writes, no env reads, no LLM calls.
    """

    def __init__(
        self,
        *,
        embedding_service: Any,
        vector_store: Any,
        bm25_index: Any,
        raw_text_store: Any,
    ) -> None:
        self._emb = embedding_service
        self._vs = vector_store
        self._bm25 = bm25_index
        self._raw = raw_text_store

    def retrieve(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
        *,
        doc_type_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """Return up to top_k chunks fused from vector + BM25 search.

        Returns [] if both retrievers return nothing (e.g. empty index).
        Never raises on empty query — returns [] instead.
        """
        if not isinstance(query, str):
            raise TypeError("query must be str")
        if not query.strip():
            return []
        if top_k < 1:
            raise ValueError("top_k must be >= 1")

        query_emb = self._emb.encode_one(query)
        vec_results = self._vs.query(query_emb, top_k=top_k * 2, doc_type_filter=doc_type_filter)
        bm25_results = self._bm25.query(query, top_k=top_k * 2)

        fused = _rrf_fuse(vec_results, bm25_results, top_k=top_k)

        chunks: list[RetrievedChunk] = []
        for (doc_id, chunk_index), score in fused:
            raw = self._raw.get_chunk(doc_id, chunk_index)
            if raw is None:
                continue
            chunks.append(RetrievedChunk(
                doc_id=doc_id,
                chunk_index=chunk_index,
                text=raw.text,
                rrf_score=score,
                title=raw.title,
                doc_type=raw.doc_type,
                source_domain=raw.source_domain,
                external_llm_context_allowed=raw.external_llm_context_allowed,
            ))
        return chunks


# ------------------------------------------------------------------
# RRF fusion
# ------------------------------------------------------------------

def _rrf_fuse(
    vec_results: list[Any],
    bm25_results: list[Any],
    top_k: int,
) -> list[tuple[tuple[str, int], float]]:
    """Reciprocal Rank Fusion — no weight tuning needed."""
    scores: dict[tuple[str, int], float] = {}

    for rank, r in enumerate(vec_results):
        key = (r.doc_id, r.chunk_index)
        scores[key] = scores.get(key, 0.0) + 1.0 / (rank + _RRF_K)

    for rank, r in enumerate(bm25_results):
        key = (r.doc_id, r.chunk_index)
        scores[key] = scores.get(key, 0.0) + 1.0 / (rank + _RRF_K)

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return ranked[:top_k]
