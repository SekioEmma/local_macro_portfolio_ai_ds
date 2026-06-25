# Era 2 RAG Manifest Remediation

`scripts/apply_rag_manifest_overrides.py` creates a derived RAG manifest with
human-confirmed canonical URLs. It never modifies the source manifest in place
and does not read staged Markdown, original PDFs, vector stores, SQLite files,
private data, environment files, or external services.

## Override Schema

Each JSONL row must contain exactly:

```json
{"document_id":"fomc_statement_2026_06_17","canonical_url":"https://www.federalreserve.gov/...","source_domain":"www.federalreserve.gov"}
```

No other fields are accepted. Overrides cannot change document type,
material type, publication dates, governance flags, file paths, summaries,
chunks, D10-D19 fields, Stage 8 fields, or AI Context Manifest eligibility.

## Rules

- `canonical_url` must be HTTPS, with no user info and a non-empty host.
- URL host and `source_domain` must match exactly after hostname
  normalization. Subdomain guessing and string containment are not used.
- Existing non-empty manifest `source_domain` must match the override.
- Existing non-empty manifest `canonical_url` is not replaced.
- Override `document_id` values must exist and be unique.
- A canonical URL cannot be reused by multiple document IDs.
- Duplicate or invalid source manifest records are audited and not silently
  repaired.
- `local_only`, `external_llm_context_allowed`, `pending_governance`, and all
  ingest eligibility fields are preserved unchanged.

Accepted overrides only add or verify:

- `canonical_url`
- `source_domain`
- `metadata_override_applied=true`

## Commands

Dry-run without writing files:

```powershell
python scripts/apply_rag_manifest_overrides.py ^
  --manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\rag_manifest.jsonl ^
  --overrides G:\local_macro_portfolio_ai\canonical_url_overrides.jsonl ^
  --output-manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\rag_manifest.derived.jsonl ^
  --audit-report G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\canonical_url_override_audit.json ^
  --dry-run ^
  --strict
```

Write a derived manifest after the audit is clean:

```powershell
python scripts/apply_rag_manifest_overrides.py ^
  --manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\rag_manifest.jsonl ^
  --overrides G:\local_macro_portfolio_ai\canonical_url_overrides.jsonl ^
  --output-manifest G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\rag_manifest.derived.jsonl ^
  --audit-report G:\local_macro_portfolio_ai\rag_staging_20260625_v2\metadata\canonical_url_override_audit.json ^
  --strict
```

`--strict` exits non-zero and writes no files when any override conflict,
invalid override, or manifest schema error is present. The audit output reports
only stable document IDs, statuses, reason codes, field names, and summary
counts; it does not include corpus text, chunks, file paths, secrets, or local
configuration.

