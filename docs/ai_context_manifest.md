# AI Context Manifest Preview

The AI context manifest is a read-only preview of what a future AI chat flow may
use as factual context. It does not call DeepSeek, Tavily, search, or any other
model/provider.

## API

- `GET /api/ai/context-preview`
- `GET /api/context/manifest`

Both paths return the same manifest.

## Included Context

- Ordinary dashboard evidence rows with `ai_context_allowed=true`
- Eligible D13 `historical_risk_percentile` rows with their lookback window,
  observation count, percentile band, robust z-score band, trigger eligibility,
  and interpretation boundary
- Eligible D14 `liquidity_funding_stress` rows with source badge, source series,
  observation date, sanitized input evidence, and interpretation boundary
- D10 `financial_stress_composite` rows as included model outputs when eligible
- D11 `pullback_systemic_risk_checklist` rows as included model outputs when eligible

Every row keeps its `source_badge`. Proxy and derived evidence is never promoted
to official evidence.
D10/D11 model outputs that include percentile context keep the nested D13
source badge, status, lookback window, band, trigger eligibility, and boundary.
D10/D11 model outputs that include D14 liquidity/funding context keep nested
source badge, source series, observation date, status, sanitized input evidence,
and boundary.

## Excluded Context

Rows are excluded when they are missing, research-only, insufficient history,
insufficient evidence, stale, blocked from AI context, or search-derived.
D14 `research_needed`, `missing`, `insufficient_evidence`, and `stale` rows are
excluded from included facts while remaining visible in evidence/audit surfaces.

The manifest explicitly excludes credentials, provider payloads, prompt text,
holdings details, holdings line items, report file contents, search results, and
private data.

## Portfolio Policy

Portfolio context is compact-summary only. Portfolio deviation rows may be used
when their metadata is complete, but holdings line items and macro attribution of
portfolio deviation remain excluded.

## Risk Boundaries

- No trading instruction.
- No crash probability.
- No recession probability.
- VIX alone is not systemic crisis.
- Equity drawdown alone is not systemic crisis.
- Proxy breadth is not true breadth.
- Financial stress score is pressure temperature, not prediction.
- Pullback checklist is risk review, not forecast.
- Portfolio deviation cannot be attributed to macro factors.
- Liquidity/funding stress rows are reference evidence, not trading signals.
- Official stress indices do not replace the project financial stress composite.
- Commercial paper spread cannot alone prove systemic crisis.
- ON RRP usage alone is not a risk trigger.
