# ADR-0006: RAG Index Generation and Embedding Compatibility

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

Phase F depends on BM25, vector retrieval, chunk storage, and document type governance staying consistent. Retrieval filters must not diverge between BM25, Chroma, and final fused results.

## Decision

RAG index generation and retrieval must preserve:

- document id and chunk id provenance;
- document type metadata;
- embedding model compatibility metadata;
- embedding dimension compatibility metadata;
- chunking version compatibility metadata;
- active index generation metadata;
- BM25, vector, and chunk-store count consistency;
- doc type filters across retrieval branches and final fusion.

## Allowed Scope

- Local-only index validation scripts.
- Deterministic fixture tests for RAG filtering and fusion.
- Manual index rebuilds when the user explicitly supplies local corpus inputs.

## Prohibited Scope

- Reading or printing raw knowledge-base text during ordinary audits.
- Mixing incompatible embedding generations in one active retrieval path.
- Querying or ingesting a nonempty active index when generation metadata is
  missing, corrupt, or incompatible with the runtime embedding model,
  dimension, or chunking version.
- Returning local-only/private documents unless explicitly allowed by the retrieval request and governance.
- Allowing BM25 results to bypass document type filters.

## Validation

- `tests/ai/test_rag_retrieval_service.py`
- `tests/ai/test_curated_rag_ingest.py`
- `tests/ai/test_local_rag_runtime_factory.py`
- `tests/ai/test_validate_local_rag_script.py`
- `tests/llm/test_vector_store.py`
- `tests/llm/test_bm25_index.py`
- `scripts/validate_local_rag.py` for local corpus/index consistency checks when real local RAG validation is requested.
