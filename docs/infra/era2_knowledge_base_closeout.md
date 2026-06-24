# Era 2 C3 Guarded Local Knowledge Base Closeout

## Scope

C3 adds a local metadata and raw-text persistence foundation for a guarded knowledge base store. It is limited to SQLite metadata at `data/knowledge_base.sqlite` and local raw text under `data/knowledge_base/raw/`, accessed only through explicit `KnowledgeBaseService` public methods.

The default knowledge-base paths are derived from the repository root, not from the current working directory, environment variables, config files, or caller input.

## Boundaries

C3 does not fetch webpages, call Tavily, accept SearchResult/provider payload input, add an API route, add frontend controls, start a scheduler, run background tasks, or perform automatic ingest.

Raw text stays only in the local raw root. It is not stored in the `documents` table, not returned by public service result objects, and not written to logs or error messages by the service.

The raw root and its parent directories must not be symlinks. The path boundary is checked before any raw-text write, raw directory creation, SQLite initialization, or SQLite connection; symlink boundaries fail closed with a stable admission error.

The `document_chunks` schema exists for later phases, but C3 does not chunk, embed, retrieve, or write `embedding_vector_id` values. C3 does not start RAG.

`data/knowledge_base.sqlite`, SQLite sidecars, and `data/knowledge_base/` are gitignored. They remain prohibited for manual reading, printing, copying, or committing outside the narrow service runtime boundary.

## Phase Handoff

C4 is still the economic-calendar phase. D1/D2/D3/D4 remain the future embedding, vector store, hybrid retrieval, and RAG-context phases.
