# Era 2 Phase D0 RAG Evidence Governance Contracts

## Scope

D0 establishes a pure, in-memory, metadata-only admission contract for
caller-supplied document descriptors that *may, in the future,* be considered
by the RAG pipeline. D0 is a governance contract layer, not a RAG runtime.

## What D0 does

- Validates the shape and typing of an 8-field descriptor:
  `document_id`, `url`, `title`, `source_domain`, `doc_type`,
  `fetched_at`, `content_sha256`, `is_stale`.
- Normalises URL (https only, no userinfo, no port, no query, no fragment,
  no path traversal, no localhost, no IP literal — same rules as the existing
  C3 knowledge-base contract).
- Normalises `source_domain` to a lowercase, dot-trimmed hostname that must
  match the canonical URL hostname exactly.
- Normalises `fetched_at` to a UTC ISO-8601 timestamp (a trailing `Z` is
  accepted and rewritten as `+00:00`).
- Applies a single fixed admission policy and returns a 8-field assessment.
- Raises `RagEvidenceGovernanceError(code=...)` on any malformed metadata.

## Fixed admission policy

Priority is strict, top to bottom:

| Condition | Eligibility | Exclusion reason |
|---|---|---|
| `is_stale == True` | `excluded` | `stale_document` |
| `doc_type == "historical_data"` | `excluded` | `historical_data_excluded` |
| `doc_type == "one_shot_news"` | `excluded` | `one_shot_news_excluded` |
| `doc_type == "policy_doc"` | `eligible` | `None` |
| `doc_type == "research_report"` | `eligible` | `None` |

Meaning:

- `historical_data` must continue to go through the existing market history
  and official history paths. It is not a future narrative corpus candidate.
- `one_shot_news` is not a future corpus candidate by default.
- Stale documents are not future corpus candidates.
- An `eligible` assessment marks a descriptor as something the future RAG
  pipeline *may* consider. It does not by itself authorise reading any
  document content.

## What D0 does NOT do

- D0 does not read raw text from any knowledge base or document store.
- D0 does not chunk text.
- D0 does not produce embeddings.
- D0 does not build any vector store.
- D0 does not run BM25 or any other lexical scorer.
- D0 does not do retrieval, ranking, similarity, or RRF fusion.
- D0 does not integrate with `ai_context_service.py`, the AI Context Manifest,
  DeepSeek, Tavily, any external provider, any API route, the frontend, or
  any Agent.
- D0 does not change the C3 raw-text local-only boundary.
- D0 does not add a CLI, a scheduler, a background task, an automatic
  ingest, or any startup-time work.
- D0 does not introduce a network client, environment-variable read,
  configuration read, secret read, database write, or filesystem read.
- D0 does not introduce any scoring, similarity, probability, weight,
  threshold, freshness metric, or trading signal.

## Inputs that are explicitly NOT D0 inputs

- Document raw content of any kind.
- Document chunk text or chunk metadata.
- Local filesystem paths or database paths.
- Provider payloads (BLS, BEA, FRED, Alpha Vantage, Tavily, etc.).
- Search results from any source.
- Private notes, holdings, account, position, transaction material.
- Prompt text, model context, or any AI-context manifest payload.
- API keys, environment variables, configuration values, secrets.

## Outputs are caller-safe metadata only

The returned `RagEvidenceAssessment` carries only:
`document_id`, `url`, `source_domain`, `doc_type`, `fetched_at`,
`content_sha256`, `eligibility`, `exclusion_reason`.

`title` is required for validation but is intentionally **not** present in
the assessment.

## Phase D sequencing

D0 must remain isolated. The remaining D-phase work is gated behind explicit,
separately-approved tasks:

- D1 — local embedding service: not started. Chunking strategy and local
  embedding choice are not decided in D0.
- D2 — vector store: not started. No vector store directory exists or is
  written by D0.
- D3 — hybrid retrieval (lexical + vector + fusion): not started.
- D4 — AI-context RAG evidence integration: not started. The AI Context
  Manifest is unchanged.
- D5 — seed corpus / cold-start ingestion: not started.

## Relationship to prior phases

- C3 guarded local knowledge-base store is unchanged. The local
  `data/knowledge_base.sqlite` and raw-text root remain accessible only
  through `knowledge_base_service.py`, and D0 does not import that service.
- C4 official-calendar acquisition is unchanged.
- AI-2 single-turn DeepSeek research path is unchanged.
- D10–D19, Stage 8, the AI Context Manifest, and Portfolio Exposure Overlay
  rules are unchanged.

## Governance summary

D0 is metadata-only. An `eligible` assessment is a future-tense governance
signal, not an authorisation to read content, not an authorisation to enter
the AI Context Manifest, and not a change to any persistence, AI-context, or
privacy rule. The frozen list of permanent boundaries in `ROADMAP.md` remains
in force.
