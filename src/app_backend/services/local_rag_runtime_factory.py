from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_backend.services.rag_retrieval_service import RAGRetrievalService
from llm.bm25_index import BM25Index
from llm.chunk_text_store import ChunkTextStore
from llm.embedding_service import EmbeddingService
from llm.vector_store import VectorStore


DEFAULT_VECTOR_DIR = Path(__file__).resolve().parents[3] / "data" / "vector_store"


@dataclass(frozen=True)
class LocalRAGRuntime:
    chunk_store: ChunkTextStore
    vector_store: VectorStore
    bm25_index: BM25Index
    embedding_service: EmbeddingService
    retrieval_service: RAGRetrievalService
    searchable_chunk_count: int


def build_local_rag_runtime(
    vector_dir: Path = DEFAULT_VECTOR_DIR,
    *,
    _bm25_factory: Any = None,
) -> LocalRAGRuntime:
    vector_dir = vector_dir.resolve()
    chunk_store = ChunkTextStore(vector_dir / "chunks.sqlite")
    chunks = chunk_store.list_chunks(external_llm_context_allowed=True)

    bm25_index = BM25Index(_bm25_factory=_bm25_factory)
    bm25_index.build([(chunk.doc_id, chunk.chunk_index, chunk.text) for chunk in chunks])

    embedding_service = EmbeddingService()
    vector_store = VectorStore(vector_dir)
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
