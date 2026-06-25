# Era 2 Curated RAG Ingest

`scripts/ingest_curated_rag_corpus.py` is the production-facing importer for
`macro-rag-corpus-curator` staging output. It is separate from
`scripts/seed_knowledge_base.py`, which remains a lightweight seed helper.

The importer reads only a curated staging root and a derived manifest such as
`metadata/derived_manifest.jsonl`. It does not read original PDFs, private
notes, holdings, outputs, provider payloads, secrets, or unrelated SQLite
databases. It does not make network requests and does not call an LLM.

The real vector root layout is:

```text
<VECTOR_ROOT>/
  chroma/
  chunks.sqlite
  ingest_audits/
```

Embedding model loading is offline-only by default. If the local
sentence-transformers model is not cached, ingest fails with
`embedding_model_not_available_offline` before any Chroma or chunk-store write.

## Hard Gates

A manifest row is ingestible only when all conditions pass:

- `extraction_status == "ready"`
- `provenance_status == "verified"`
- `ingest_status == "eligible"`
- `external_llm_context_allowed == true`
- `allowed_use == "external_context_candidate"`
- `runtime_doc_type in {"policy_doc", "research_report"}`
- `canonical_url` is non-empty
- `source_domain` exactly matches the canonical URL host
- `cleaned_content_sha256` matches the staged Markdown bytes
- `document_id` is unique across the manifest
- `output_relpath` stays inside `policy_doc/` or `research_report/`

Rows in `pending_governance`, `review_required`, `local_only`, `unsupported`,
or with duplicate document IDs are not ingested. `local_only` rows are never
written to the external-LLM reachable RAG path.

## Commands

Dry-run:

```powershell
python scripts/ingest_curated_rag_corpus.py `
  --curated-root G:\local_macro_portfolio_ai\rag_staging_20260625_v2 `
  --manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\derived_manifest.jsonl `
  --vector-root G:\local_macro_portfolio_ai\local_macro_portfolio_ai_ds\data\vector_store `
  --dry-run `
  --strict
```

Write after a clean preflight:

```powershell
python scripts/ingest_curated_rag_corpus.py `
  --curated-root G:\local_macro_portfolio_ai\rag_staging_20260625_v2 `
  --manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\derived_manifest.jsonl `
  --vector-root G:\local_macro_portfolio_ai\local_macro_portfolio_ai_ds\data\vector_store `
  --write `
  --strict `
  --offline-only
```

Validate local indexes:

```powershell
python scripts/validate_local_rag.py `
  --curated-root G:\local_macro_portfolio_ai\rag_staging_20260625_v2 `
  --manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\derived_manifest.jsonl `
  --vector-root G:\local_macro_portfolio_ai\local_macro_portfolio_ai_ds\data\vector_store
```

If the derived manifest has zero eligible documents, ingest exits non-zero and
writes nothing. The correct behavior is no vector write and skipped retrieval
smoke tests until the manifest and local offline embedding model are ready.
