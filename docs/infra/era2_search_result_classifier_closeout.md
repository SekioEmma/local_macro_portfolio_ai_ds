# Era 2 C1 Search Result Classifier Closeout

## Scope

C1 adds only deterministic document-type classification for a single guarded search result. It maps a `SearchResult` into one of five fixed categories: `historical_data`, `policy_doc`, `research_report`, `one_shot_news`, or `discard`.

The classifier is not a fact checker, content truth test, investment signal, or AI evidence eligibility gate. Its output does not say whether the page is accurate, current, complete, useful, or suitable as model evidence.

## Boundaries

- C1 does not write SQLite.
- C1 does not save search results.
- C1 does not save raw URL, title, snippet, provider payload, or classification output.
- C1 does not trigger network access.
- C1 does not call Tavily.
- C1 does not add or connect any API route.
- Unknown, risky, malformed, or static-rule-mismatched URLs always classify as `discard`.

The existing B7 runtime policy, sanitizer, allowlist, budget, and response guard remain unchanged. C1 only classifies a `SearchResult` object already supplied by another layer.

## Phase Handoff

C2 is the first phase that may handle official historical financial data ingest, subject to its own guardrails and approval boundaries. C3 is the first phase that may handle knowledge-base persistence.

C1 does not start C2, C3, RAG, agent runtime work, frontend work, background refresh, caching, or provider integration.
