# P-M4-D AI Context Manifest Cache Review

## Scope

Review-only decision audit. No runtime Manifest cache implemented.

## Decision

**P-M4-D implementation deferred. Return to S2.**

The P-M4-C in-process summary/evidence cache already eliminates the Manifest
performance bottleneck. Manifest-specific work is pure in-memory row
classification (~26 ms warm, ~2 ms when evidence is pre-loaded via pipeline
context). Adding a dedicated Manifest cache would introduce stale/privacy/AI
context eligibility risk with no meaningful performance gain.

## 4.1 Current Call Path

### Routes that call `build_ai_context_manifest`

1. **`GET /api/context/manifest`** (`main.py:104`) — calls
   `ai_context_service.build_ai_context_manifest()` with no context argument.
2. **AI preview routes** (`ai_preview_service.py`) — four preview endpoints
   (`context-preview`, `preview-chat`, `preview-memo`, `preview-report`) each
   call `build_ai_context_manifest()` independently with no context argument.

### How `build_ai_context_manifest` works

1. If a `DashboardPipelineContext` with a pre-loaded evidence table is passed,
   it reuses that evidence table directly.
2. Otherwise it calls `build_dashboard_evidence_table(write_last_good=False)`.
3. After P-M4-C, step 2 hits the process-local single-slot cache when the
   cache key matches (default path, `write_last_good=False`).
4. The Manifest-specific work iterates ~219 evidence rows and classifies them
   into included/excluded facts and model outputs. This is pure in-memory with
   no DB queries, no file I/O, and no network.

### Does P-M4-C already benefit Manifest?

**Yes.** The expensive part of `build_ai_context_manifest` is
`build_dashboard_evidence_table`, which is now cached by P-M4-C. Warm Manifest
calls already complete in ~26 ms (down from ~3350 ms cold). The
Manifest-specific classification itself takes ~2 ms.

### Do AI preview routes reuse Manifest?

**No.** Each preview route rebuilds the Manifest independently. However, since
each call hits the P-M4-C evidence cache, the rebuild cost is only ~26 ms per
call. This is not a meaningful bottleneck for the current local-first single-
user architecture.

## 4.2 Performance After P-M4-C

### Manifest timing measurements

| Call | Time (ms) | included_facts | excluded_facts | included_model_outputs | excluded_model_outputs |
|---|---|---|---|---|---|
| cold | 3350 | 119 | 22 | 63 | 15 |
| warm1 | 27 | 119 | 22 | 63 | 15 |
| warm2 | 33 | 119 | 22 | 63 | 15 |
| warm3 | 26 | 119 | 22 | 63 | 15 |

Cold = first call (evidence cache empty). Warm = subsequent calls (evidence
cache populated). Warm calls are ~99% faster than cold.

### Benchmark pipeline timing

| Metric | Value |
|---|---|
| evidence_row_count | 219 |
| included_facts_count | 119 |
| included_model_outputs_count | 63 |
| dashboard_evidence_table_ms | 3163 |
| ai_context_manifest_ms (benchmark, uses pipeline context) | 25 |
| shared_ai_context_manifest_ms (with pre-loaded evidence) | 2 |

### Assessment

Manifest warm path is not a meaningful bottleneck. The ~26 ms cost is dominated
by defensive copy overhead and row iteration, not by avoidable rebuilds. A
Manifest cache would save at most ~24 ms per call (the difference between
~26 ms warm and ~2 ms with pre-loaded evidence), which is not material for the
current local single-user architecture.

## 4.3 Semantic Risk

Manifest cache would carry higher risk than summary/evidence cache because it
directly serves the AI context consumption chain:

| Concern | Risk Level | Notes |
|---|---|---|
| `ai_context_allowed` | **high** | Manifest inclusion/exclusion directly derives from evidence rows. A stale cached Manifest could include rows that should be excluded after a freshness change, or exclude rows that became available. |
| `included_facts` / `excluded_facts` | **high** | Counts and content are the contract for AI preview and memo surfaces. Stale Manifest could serve wrong inclusion lists. |
| `included_model_outputs` / `excluded_model_outputs` | **high** | Model outputs change when upstream models re-run with updated data. |
| `freshness_status` | **medium** | Freshness can change between calls if report files are updated. Evidence cache already handles this via file signature invalidation, but a separate Manifest cache key would need to track the same signatures. |
| `source_badge` | **medium** | Unlikely to change between calls in practice, but a stale Manifest could serve outdated badge values. |
| `blocked_reason` | **medium** | Derives from evidence row state; stale evidence → stale blocked reasons. |
| `missing` / `research_needed` / `stale` / `insufficient_history` / `not_available` handling | **high** | These statuses must remain excluded. A Manifest cache that drifts from evidence state could accidentally include rows with these statuses. |
| Privacy boundary | **medium** | Manifest itself contains only sanitized evidence snapshots. However, a separate cache layer increases the surface area where privacy-relevant data could be inadvertently retained. |
| External AI boundary | **low** | Manifest cache would be local-only and would not open external AI paths. But it adds complexity near the AI context surface. |

### Summary

The primary risk is **inclusion/exclusion drift**: if evidence rows change
(e.g., a report file is updated and the evidence cache is invalidated) but a
Manifest cache retains stale inclusion lists, AI previews and memos could
operate on incorrect context. This risk is avoidable if the Manifest cache key
is identical to the evidence cache key, but that makes the Manifest cache
redundant — it would just be a defensive copy of work that takes ~26 ms.

## 4.4 Minimum Safe Implementation (if ever needed)

If future profiling proves Manifest caching is needed, the minimum safe design:

1. **Derive Manifest only from cached current unfiltered evidence table.** Do
   not introduce a separate Manifest cache key; invalidation must follow the
   evidence cache key exactly.
2. **No prompt-aware cache.** Manifest does not depend on user prompts.
3. **No external AI payload cache.** Manifest is local evidence only.
4. **No private account/holdings expansion.** Manifest already uses sanitized
   compact context.
5. **No schema change.** `AIContextManifestResponse` stays unchanged.
6. **Defensive copy** on cache get, same pattern as evidence cache.
7. **Invalidation follows evidence cache key.** When evidence cache is
   invalidated, Manifest cache is also invalidated.
8. **Contract tests** must verify `included_facts_count`,
   `excluded_facts_count`, `included_model_outputs_count`,
   `excluded_model_outputs_count` match between cached and uncached paths.
9. **Route responses must not expose cache diagnostics.**

## 4.5 Decision

### Evaluation against implementation thresholds

| Threshold | Met? | Notes |
|---|---|---|
| Repeated Manifest calls remain a meaningful bottleneck after P-M4-C | **No** | Warm Manifest is ~26 ms; Manifest-specific work is ~2 ms. |
| Cold/warm timing shows material avoidable Manifest-only overhead | **No** | The ~24 ms gap is defensive copy + row iteration, not avoidable rebuild. |
| Implementation can avoid new public schema, new cache keys, and Manifest-specific stale risk | **Possible** | Could piggyback on evidence cache key. But the benefit is ~24 ms. |
| Tests can prove included/excluded counts and privacy boundaries unchanged | **Yes** | Straightforward to test. But testing cost exceeds the ~24 ms benefit. |

### Recommended decision

**Defer P-M4-D implementation and return to S2.**

All four thresholds are not simultaneously met. The primary threshold — that
Manifest remains a meaningful bottleneck — is clearly not met. The P-M4-C
evidence cache already provides the dominant performance benefit. Adding a
Manifest cache would introduce stale/privacy/AI context eligibility risk for a
~24 ms saving that is not material in the current architecture.

### Conditions for revisiting

Revisit only if:

- The project moves to a multi-user or high-concurrency architecture where
  ~26 ms per Manifest call becomes material.
- Profiling shows Manifest row iteration is a measurable hotspot (currently
  it is not).
- A new consumer requires sub-millisecond Manifest access.

## What Does Not Change

- no AI Context Manifest semantics changed
- no `ai_context_allowed` rules changed
- no `included_facts` / `excluded_facts` semantics changed
- no `included_model_outputs` / `excluded_model_outputs` semantics changed
- no runtime Manifest cache implemented
- no model semantics changed
- no public output keys changed
- no module/model/metric/registry keys changed
- no endpoint/frontend/external AI added
- no live fetch/write
- no Stage 9 reopened
- no prediction/probability/trading outputs added

## Status

P-M4-D AI Context Manifest cache review: completed as review-only.
P-M4-D implementation: deferred.
Next recommended task: S2 Scenario Stress Matrix explanation tests / golden
contract integration.
