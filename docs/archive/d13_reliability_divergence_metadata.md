# DF-4 D13 Reliability / Divergence Metadata

## Scope

DF-4 adds reliability and method-divergence metadata to D13
`historical_risk_percentile` rows. It does not rewrite D13, does not add new
providers, does not change percentile / z-score / robust z-score formulas, does
not change 5Y/3Y lookback rules, does not change band thresholds, and does not
add endpoints, frontend UI, external AI, Tavily/search, persistence, prediction
output, probability output, allocation directives, or trading advice.

The new metadata is explanatory model-quality context for downstream
D10 / D11 / D15 / D16 / D19 / AI Context consumers. It cannot promote a D13 row
to a hard trigger and cannot relax existing AI context eligibility.

## Current D13 Model

D13 already exposes:

- empirical `percentile` with `percentile_band`
- `zscore` with `zscore_band`
- `robust_zscore` (median + MAD) with `robust_zscore_band`
- 5Y preferred / 3Y fallback lookback with `history_quality_status`
  (`sufficient` / `limited_history` / `insufficient_history`)
- `percentile_direction` (`higher_is_more_stress` / `lower_is_more_stress`)
- `trigger_eligibility` and `ai_context_tier` derived from source badge and
  history quality
- `interpretation_boundary` and `ai_context_allowed`

DF-4 does not modify any of these. It only adds new metadata fields.

## New Fields (top-level and `component_contributions`)

- `reliability_band`: `high` / `medium` / `low` / `insufficient`
- `reliability_drivers`: sorted list of categorical drivers (history, source,
  method availability, divergence, blocking reasons)
- `divergence_band`: `none` / `mild` / `material` / `not_available`
- `divergence_notes`: short human-readable description of method agreement; no
  probability or trading language
- `method_agreement`: `all_available_aligned` / `mostly_aligned` / `mixed` /
  `divergent` / `insufficient_methods`
- `normalization_methods_available`: `{percentile, zscore, robust_zscore}`
  booleans
- `percentile_zscore_alignment`,
  `percentile_robust_zscore_alignment`,
  `zscore_robust_zscore_alignment`: each is one of `aligned` /
  `mildly_divergent` / `materially_divergent` / `not_available`
- `source_quality_note`: free text describing latest input `source_badge` and
  `trigger_eligibility`
- `history_window_note`: free text describing `lookback_window`,
  `history_quality_status`, and `observation_count` vs minimum

These fields are also propagated through `sanitized_d13_context`, so D10 / D11 /
D15 / D16 that read sanitized auxiliary context see the metadata.

## DF-4c Credit OAS Coverage Metadata

DF-4c extends the same metadata pattern for credit OAS coverage and provider
rebuild diagnostics. It adds these fields to every D13 row and to
`component_contributions`:

- `history_coverage_status`
- `provider_rebuild_status`
- `normalization_availability`
- `coverage_diagnostics`
- `credit_reference_role`
- `substitution_policy`
- `long_history_reference_status`

For `high_yield_spread` and `investment_grade_spread`, a 1094-day local sample
remains blocked as `insufficient_history` with
`history_coverage_status=below_exact_gate`, `provider_rebuild_status=
provider_rebuild_limited`, `substitution_policy=no_substitution`, and
`long_history_reference_status=unavailable_for_primary_series`.

`normalization_availability.current_level_available=True` can coexist with
percentile/z-score/robust-z availability all being false. This explains why the
current OAS level exists while historical normalization remains blocked.

`BAA10Y` is documented as `long_history_credit_proxy_reference` with
`proxy_reference_not_oas_substitute`; it does not replace HY/IG OAS.

## Broad Band Mapping

To compare percentile_band / zscore_band / robust_zscore_band without crossing
band semantics, each band is mapped to a broad stress level:

| Band         | Broad Level |
|--------------|-------------|
| `low_extreme`| -1          |
| `normal`     |  0          |
| `elevated`   |  1          |
| `high`       |  2          |
| `extreme`    |  3          |
| `None`       | `not_available` |

`lower_is_more_stress` direction is already handled by the existing band
helpers, so DF-4 does not invert direction again. Drawdown rows keep the
existing semantic: lower percentile means more stress.

## Pairwise Alignment Rule

Pairwise alignment between two available method levels uses absolute level
difference:

- 0  → `aligned`
- 1  → `mildly_divergent`
- ≥2 → `materially_divergent`
- any side `None` → `not_available`

`divergence_band` summarizes across all available methods:

- diff 0 across all available → `none`
- diff 1 → `mild`
- diff ≥ 2 → `material`
- fewer than two methods available → `not_available`

`method_agreement` summarizes the same span as a categorical label:

- single available method or none → `insufficient_methods`
- max diff 0 → `all_available_aligned`
- max diff 1 → `mostly_aligned`
- max diff 2 → `mixed`
- max diff ≥ 3 → `divergent`

## Reliability Band Cascade

`reliability_band` is decided by a strict cascade. The first matching rule
wins.

1. `insufficient` if any of:
   - `status` is one of `missing`, `research_needed`, `not_available`,
     `insufficient_history`, `stale`
   - `history_quality_status` is not `sufficient` or `limited_history`
   - no normalization method is available
2. `low` if any of:
   - latest input `source_badge == proxy`
   - `divergence_band == material`
   - two or more methods unavailable
   - `history_quality_status == limited_history` AND `divergence_band == mild`
3. `medium` if any of:
   - `history_quality_status == limited_history`
   - latest input `source_badge == unofficial_fallback`
   - one method unavailable
   - `divergence_band == mild`
4. `high` otherwise.

`reliability_band == high` is descriptive only. It does not create a new hard
trigger and does not change `trigger_eligibility`, `ai_context_allowed`, or
band thresholds.

## AI Context Boundary

- DF-4 does not change existing `ai_context_allowed` rules.
- `missing`, `stale`, `insufficient_history`, `not_available` rows remain
  excluded from factual context (`ai_context_allowed=False`,
  `ai_context_tier=excluded`).
- `reliability_band == insufficient` is consistent with these rows.
- `divergence_band == material` does not silently revoke eligibility. It
  becomes a downgrade note in `reliability_drivers` and `divergence_notes` for
  AI memo and downstream consumers to surface, but the row remains eligible if
  the existing rules already accept it.
- Metadata fields never imply probability, forecast, market direction,
  expected return, or trading instruction.

## Trigger Eligibility Boundary

- `trigger_eligibility=hard_trigger_allowed` remains gated by official /
  official_fallback source badge AND sufficient or limited history. DF-4 does
  not allow `proxy`, `unofficial_fallback`, `insufficient_history`,
  `not_available`, `stale`, or `missing` to upgrade to a hard trigger.
- `divergence_band == material` does NOT auto-revoke `hard_trigger_allowed`,
  because the existing project boundary is that explanation, not a new
  trigger, is the right response to method divergence. Downstream modules can
  read `reliability_band` and `divergence_band` to choose how to phrase
  derived evidence.

## Examples

### Official 5Y aligned methods

- `history_quality_status=sufficient`, `source_badge=official`
- all three methods available, all bands at the same broad level
- `divergence_band=none`, `method_agreement=all_available_aligned`
- `reliability_band=high`
- existing `trigger_eligibility=hard_trigger_allowed`
- existing `ai_context_allowed=True`

### Limited 3Y history

- `history_quality_status=limited_history`, `source_badge=official`
- all methods available, aligned
- `divergence_band=none`, `method_agreement=all_available_aligned`
- `reliability_band=medium`
- existing `trigger_eligibility=hard_trigger_allowed`
- existing `ai_context_allowed=True`

### Percentile high but robust-z normal

- heavy-tailed distribution, latest near top of the dense cluster
- `percentile_band=high`, `zscore_band=normal`, `robust_zscore_band=normal`
- `divergence_band=material`, `method_agreement=mixed`
- `reliability_band=low`
- existing `trigger_eligibility` unchanged
- existing `ai_context_allowed` unchanged; divergence is explanatory

### Zero std / zero MAD

- constant series; `zscore` or `robust_zscore` becomes `None`
- row status becomes `not_available` for the affected kind
- `reliability_band=insufficient`, `divergence_band=not_available`
- existing `ai_context_allowed=False`

### Proxy source

- `source_badge=proxy`
- `reliability_band=low`
- existing `trigger_eligibility=proxy_auxiliary_only`
- existing `ai_context_tier=auxiliary_context`

### Insufficient history

- `status=insufficient_history`, all method bands `None`
- `reliability_band=insufficient`, `divergence_band=not_available`,
  `method_agreement=insufficient_methods`
- existing `ai_context_allowed=False`,
  `trigger_eligibility=not_eligible`

## Final Decision

D13 reliability and divergence metadata is descriptive model-quality context.
It cannot create new hard triggers, cannot relax AI context eligibility,
cannot upgrade proxy or insufficient rows, and cannot imply probability,
forecast, market direction, expected return, or trading instruction. Material
divergence should be explained as method disagreement, not traded.

## Next Step

DF-4 closes Stage DF as planned. Subsequent work returns to the broader
modeling roadmap; future scenario stress or AI memo improvements should
continue to honor the same boundaries.
