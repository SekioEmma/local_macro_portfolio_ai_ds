# Per-key Last-good Cache

The per-key last-good cache is a local file cache for the most recent usable value of an individual Dashboard metric.
It is a foundation for future fallback work; it does not replace current Dashboard values in this phase.

## Purpose

The existing whole-snapshot cache can tell the app that a full report is stale.
The per-key cache keeps a narrower record: the last metric value that passed Dashboard evidence quality gates.

This helps the audit layer report when a missing current metric has a prior usable value, without pretending that the prior value is live data.

## Storage

Default path:

```text
data/cache/last_good/{safe_metric_key}.json
```

Only `.gitkeep` files are tracked under `data/cache`.
Real `data/cache/last_good/*.json` files are ignored and must not be committed.

## Schema

Each JSON file contains only safe metadata:

- `metric_key`
- `value`
- `value_text`
- `unit`
- `status`
- `source`
- `source_badge`
- `provider`
- `source_series`
- `observation_date`
- `generated_at`
- `fetched_at`
- `freshness_status`
- `ttl_policy`
- `ttl_days`
- `stale_after`
- `last_live_status`
- `last_error`
- `raw_hash`

The cache does not store raw provider responses, raw prompts, raw holdings, full reports, API keys, or complete project roots.

## Save Rules

A metric may be saved only when it has:

- a safe metric key
- a non-null value
- status `ok`, `watch`, `pressure`, or `stress`
- a source badge that is not `missing`, `research_needed`, `search-derived`, or `proxy`
- either `observation_date` or `generated_at`

The Dashboard integration saves candidates only from current evidence rows that are eligible for the AI factual context boundary.
`portfolio_deviation` rows are excluded from this cache because local portfolio compact facts should not be managed as market last-good data.

## TTL Policy

- daily market metrics use `ttl_policy=daily` and `ttl_days=7`
- monthly macro metrics use `ttl_policy=monthly` and `ttl_days=75`
- unknown frequency uses `ttl_policy=unknown`, no TTL days, and is classified conservatively as `stale`

Load status is one of:

- `usable`
- `stale`
- `expired`
- `unavailable`
- `error`

Corrupted JSON returns `error` and does not crash the caller.

## Semantics Boundary

Last-good is not the current live value.
This phase does not use last-good to replace Dashboard values, evidence-table values, provider results, portfolio data, or memo context.

When audit finds a missing current metric with last-good available, it reports `last_good_available_but_not_used` semantics through the `metrics_missing_but_last_good_available` and `last_good_not_used_count` fields.

Future integration may add explicit fallback UI or historical-store behavior, but it must label last-good freshness separately and must not promote it into the official current layer without a dedicated review.

## Privacy Boundary

The cache stores only whitelisted fields.
It ignores extra fields such as `raw_extra`, API-key-like fields, holdings payloads, raw output reports, and prompt content.

The cache is local-only, file-based, and does not call providers, DeepSeek, Tavily, or search.
