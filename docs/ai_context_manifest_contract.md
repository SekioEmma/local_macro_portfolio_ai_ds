# AI Context Manifest Contract

## Role

AI Context Manifest is the only approved context boundary for Stage 9. It is a
read-only contract over audited evidence rows, compact model outputs, explicit
exclusions, privacy policies, and risk boundaries. Stage 9 must consume this
manifest instead of raw dashboard payloads, holdings files, provider payloads,
SQLite databases, cache files, or prompts.

## Included Facts

Included facts must satisfy all of these conditions:

- Valid source, freshness, and status metadata.
- `ai_context_allowed=true`.
- Not stale.
- Not missing.
- Not `research_needed`.
- Not `insufficient_history`.
- Not private.
- Not raw provider data.
- Not search-derived unless explicitly permitted in a future search phase.

Included facts may support memo/report summaries only within their displayed
source badge, freshness, trigger eligibility, and interpretation boundary.
Proxy or derived evidence must never be promoted to official evidence.

## Excluded Facts

Excluded facts include:

- Missing rows.
- `research_needed` rows.
- `insufficient_history` rows.
- Stale rows.
- Blocked rows.
- Proxy-only rows that cannot be factual support.
- Search-derived rows unless a future Tavily phase explicitly allows cited
  search material.
- Private inputs.
- Holdings line items.
- Raw payloads.

Excluded facts may be summarized as constraints, missing inputs, blocked inputs,
or research gaps. They must not become factual support.

## Included Model Outputs

Included model outputs are compact D10-D19 and Stage 8 model-output rows only
when eligible for AI context. They must preserve `interpretation_boundary` and
their model/formula version metadata when available.

Included model outputs must not expose internal scores that are intentionally
private. They must not expose forbidden language or action, probability, or
return fields.

## Excluded Model Outputs

Excluded model outputs include:

- `private_inputs_excluded`.
- `insufficient_evidence` when policy blocks it from model-output support.
- Missing or `research_needed` placeholder rows.
- Large replay payloads.
- Daily historical replay details.
- Raw scenario internals when not public.
- Any row that could be misread as action, probability, or return output.

Excluded model outputs may be referenced only as constraints or exclusions.

## Stage 8 Portfolio Exposure Contract

`portfolio_exposure_overlay` can be used only as a sanitized compact
explanatory overlay. It may describe macro-channel mapping, exposed constraints,
and supporting evidence already eligible in the manifest.

It must preserve these hard boundaries:

- No holdings line items.
- No account values.
- No position weights.
- No target allocation.
- Cannot create D15 support.
- Cannot change D16 scenario severity.
- Cannot create D19 availability.
- Missing sanitized portfolio context must remain visible and must not become
  low or high exposure.

## D15 Contract

D15 remains current evidence review. It is not a classifier, forecast model,
event-odds model, trading model, or allocation engine. Stage 9 may summarize
D15 labels, support bands, evidence quality, conflicts, missing inputs, and
blocked inputs only within the D15 interpretation boundary.

## D16 Contract

D16 remains a deterministic scenario matrix and current evidence transmission
review. It is not a forecast, event-odds model, probability model, return model,
or strategy model. Stage 9 must not convert scenario severity or uncertainty
bands into future probabilities.

## D17 Contract

D17 remains growth/inflation context. It is not a recession call, inflation
forecast, event-odds model, allocation directive, or return estimate. Missing
and research-needed inputs must remain visible.

## D18 Contract

D18 remains valuation/equity-structure research and proxy context. It is not a
timing model, valuation call, probability model, allocation directive, or return
estimate. Proxy breadth/concentration does not replace true breadth, and
valuation research gaps must remain constraints.

## D19 Contract

D19 remains historical replay and boundary validation. It is not probability
calibration, prediction backtesting, trading performance review, strategy
evaluation, or future market forecasting. Stage 9 may use compact validation
counts and boundary summaries, not large replay details or daily replay payloads.

## Search-Derived Material

Search-derived material is excluded by default. A future Tavily phase may allow
cited search material only when the query is explicit, no account or portfolio
context is sent, citations are preserved, and search failure does not create
facts.
