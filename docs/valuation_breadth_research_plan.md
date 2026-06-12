# Valuation and Breadth Research Plan

This plan defines conservative data boundaries for valuation, breadth, concentration, and crash-confirmation evidence.
It is a research and implementation plan only.
It does not add live providers, fetch valuation data, change Dashboard values, or promote proxy/yfinance data to official evidence.

## Current Coverage Boundary

The current pipeline already has usable evidence for rates, real yields, inflation, official WTI/Brent energy history, labor, credit, equity trend, and portfolio deviation.
The remaining high-value gaps are:

- valuation level
- earnings expectations and revisions
- true market breadth
- market concentration
- tail-risk confirmation

These gaps should remain explicit in audit and AI context until reliable dated sources or carefully labelled proxy calculations exist.

## Classification Summary

| Category | Meaning | AI factual context default |
| --- | --- | --- |
| `implement_now_from_existing_history` | Can be derived from already configured local `market_history` inputs after enough observations exist. | Allowed only as labelled `derived`/`proxy` context, never as official fact. |
| `implement_later_with_proxy` | Feasible from proxy ETFs or locally stored history, but needs new metric specs, labels, tests, and audit gates. | Block until explicit proxy semantics are implemented. |
| `research_needed` | Needs a reliable dated source or rule before use. | Always blocked. |
| `manual_or_search_derived_only` | Could be manually entered or search/citation derived later, but not trusted as automated evidence yet. | Block by default until a citation/manual review layer exists. |
| `not_for_mvp` | Useful in theory but too broad, expensive, fragile, or product-distracting for current MVP. | Block. |

## Candidate Metrics

### Valuation

| Metric | Classification | Candidate source path | Boundary |
| --- | --- | --- | --- |
| S&P 500 trailing PE | `research_needed` | Possible public research source, manual entry, or future citation layer. | Do not fabricate from price index alone; needs dated earnings denominator and source. |
| S&P 500 forward PE | `research_needed` | FactSet/S&P/analyst-consensus source research. | Keep missing until reliable source is identified; no consensus claims without source. |
| CAPE / Shiller PE | `research_needed` | Public research source candidate, likely Robert Shiller dataset or equivalent documented source. | Needs source review, date, unit, and redistribution boundary. |
| Earnings yield | `research_needed` | Could derive only after PE or earnings denominator is sourced. | Do not compute from price-only data. |
| Equity risk premium proxy | `research_needed` | Could derive only after earnings yield plus Treasury/real-yield basis is defined. | Must label assumptions; not an official ERP. |
| Nasdaq 100 valuation proxy | `manual_or_search_derived_only` | Possible public research/manual source. | QQQ price return is not valuation; keep PE/CAPE claims blocked. |

### Breadth and Concentration

| Metric | Classification | Candidate source path | Boundary |
| --- | --- | --- | --- |
| SPY 30D / 60D return | `implement_now_from_existing_history` | `spy_proxy` from `configs/yfinance_history.yaml`; calculate period return from local `market_history`. | Proxy ETF return, not official S&P 500 index fact. |
| RSP 30D / 60D return | `implement_now_from_existing_history` | `rsp_proxy` from local yfinance history. | Equal-weight ETF proxy; not true breadth. |
| QQQ 30D / 60D return | `implement_now_from_existing_history` | `qqq_proxy` from local yfinance history. | Nasdaq 100 ETF proxy; not valuation. |
| SPY vs RSP 30D / 60D relative return | `implement_now_from_existing_history` | Relative return of `spy_proxy` minus `rsp_proxy`. | Concentration/breadth proxy only; does not measure constituent-level advance/decline. |
| QQQ vs SPY 30D / 60D relative return | `implement_now_from_existing_history` | Relative return of `qqq_proxy` minus `spy_proxy`. | Growth/mega-cap tilt proxy only. |
| Top-heavy / mega-cap concentration proxy | `implement_later_with_proxy` | Could use QQQ vs SPY, SPY vs RSP, or selected mega-cap ETF proxy basket later. | Proxy must not be called top-10 S&P weight. |
| Sector concentration proxy | `implement_later_with_proxy` | Sector ETF relative-return proxies if added later. | Not constituent weight data; needs separate labels. |
| Advance/decline line | `research_needed` | Requires reliable breadth dataset/source. | yfinance ETF returns cannot substitute for true advance/decline. |
| 52-week highs/lows | `research_needed` | Requires reliable exchange/index breadth dataset. | Do not infer from SPY/QQQ/RSP alone. |
| Top 10 S&P 500 weight | `research_needed` | S&P/ETF holdings/public research source review. | Keep blocked unless reliable dated holdings/weight source is identified. |

### Risk and Crash Confirmation

| Metric | Classification | Candidate source path | Boundary |
| --- | --- | --- | --- |
| VIX | Existing covered evidence | Current FRED/public path and compact Dashboard evidence. | Volatility signal only; not crisis confirmation by itself. |
| Credit spreads | Existing covered evidence | High-yield and investment-grade spreads from current public/FRED path. | Credit stress confirmation requires multiple signals. |
| SKEW / tail risk | `research_needed` | CBOE/public source research. | Optional later phase; do not add without source and freshness rules. |
| HYG vs LQD relative return | `implement_now_from_existing_history` | `hyg_proxy` minus `lqd_proxy` from local yfinance history. | ETF proxy for credit-risk appetite, not official spread. |
| SPY drawdown | `implement_later_with_proxy` | Local `spy_proxy` history or existing `sp500` history. | Needs explicit peak/window rule; proxy if using SPY. |
| Nasdaq drawdown | `implement_later_with_proxy` | Local `qqq_proxy`, `nasdaq`, or `nasdaq100` history. | Needs explicit peak/window rule. |
| Breadth deterioration | `implement_later_with_proxy` for proxy; `research_needed` for true breadth | SPY vs RSP and QQQ vs SPY can provide proxy deterioration; true breadth needs source. | Must distinguish proxy deterioration from constituent breadth. |
| Credit stress confirmation | Existing partial evidence plus future proxy | Current spreads; HYG vs LQD proxy can add context later. | Crisis confirmation should require credit plus volatility plus breadth/earnings/labor context. |

## Existing-History Proxy Opportunities

The following can be implemented in a future code phase without live provider work because their dependencies are already configured for local yfinance history:

| Future metric key suggestion | Dependencies | Calculation | Badge |
| --- | --- | --- | --- |
| `spy_proxy_30d_return` | `spy_proxy` | 30D period return | `derived` from `proxy` dependency |
| `spy_proxy_60d_return` | `spy_proxy` | 60D period return | `derived` from `proxy` dependency |
| `rsp_proxy_30d_return` | `rsp_proxy` | 30D period return | `derived` from `proxy` dependency |
| `rsp_proxy_60d_return` | `rsp_proxy` | 60D period return | `derived` from `proxy` dependency |
| `qqq_proxy_30d_return` | `qqq_proxy` | 30D period return | `derived` from `proxy` dependency |
| `qqq_proxy_60d_return` | `qqq_proxy` | 60D period return | `derived` from `proxy` dependency |
| `spy_vs_rsp_30d` | `spy_proxy`, `rsp_proxy` | 30D relative return | `derived` from `proxy` dependencies |
| `spy_vs_rsp_60d` | `spy_proxy`, `rsp_proxy` | 60D relative return | `derived` from `proxy` dependencies |
| `qqq_vs_spy_30d` | `qqq_proxy`, `spy_proxy` | 30D relative return | `derived` from `proxy` dependencies |
| `qqq_vs_spy_60d` | `qqq_proxy`, `spy_proxy` | 60D relative return | `derived` from `proxy` dependencies |
| `hyg_vs_lqd_30d` | `hyg_proxy`, `lqd_proxy` | 30D relative return | `derived` from `proxy` dependencies |
| `hyg_vs_lqd_60d` | `hyg_proxy`, `lqd_proxy` | 60D relative return | `derived` from `proxy` dependencies |

V1 implementation status:

- Implemented as local-only historical derived metrics in `breadth_concentration_proxy`.
- Surfaced in Dashboard summary and Evidence Table as proxy-derived rows.
- Audited through the `proxy_breadth` block in `scripts/audit_data_pipeline_coverage.py`.

Implementation notes:

- Add specs to `historical_derived_metrics` only after tests define proxy dependency policy.
- Use `source=local_market_history` and `source_badge=derived`.
- Carry dependency source badges and source series into audit output.
- Keep interpretation hints explicit: yfinance ETF proxy, not official index breadth, valuation, or concentration weight.
- Set `ai_context_allowed=true` only when source/date/freshness/hint metadata are complete and the wording is proxy-safe.

## Research-Needed Metrics

These should remain blocked until a reliable dated source is selected:

- S&P 500 forward PE
- earnings revision
- analyst EPS growth
- true market breadth advance/decline
- 52-week highs/lows breadth
- top 10 S&P 500 weight
- FedWatch probability
- PPI final demand YoY history, unless enough verified `PPIFIS` index history is present
- CAPE / Shiller PE, until source and redistribution boundary are documented
- SKEW / tail risk, until source and freshness policy are documented

## Source Badge Policy

| Badge | Use |
| --- | --- |
| `official` | Government, exchange, or official index/agency source with dated observation and clear definition. |
| `public_research` | Reliable public research dataset with documented methodology, date, and redistribution boundary. |
| `unofficial_fallback` | Non-official market data fallback, such as yfinance index history. |
| `proxy` | ETF or instrument used as a proxy for an exposure, not the underlying official measure. |
| `derived` | Local calculation from stored dependencies; must expose dependency keys and calculation. |
| `search-derived` | Search/citation-derived value; blocked by default until citation layer exists. |
| `manual` | Human-entered dated value with source note; blocked unless review rules allow it. |
| `research_needed` | Metric is intentionally unavailable pending source/rule research. |

Proxy and unofficial fallback inputs must never be shown as `official`.
Derived metrics inherit their trust boundary from their dependencies and their interpretation hint.

## AI Factual Context Policy

- `official` and `public_research` can be allowed when value, date, source, freshness, and interpretation boundary are complete.
- `derived` can be allowed only when dependencies are complete and the hint states calculation and source boundary.
- `proxy`-based derived metrics can be allowed only as proxy context; they must not support official valuation, official breadth, or concentration-weight claims.
- `unofficial_fallback` should remain clearly labelled and should not override official current evidence.
- `search-derived` should be blocked by default until a Tavily/citation layer exists.
- `manual` should be blocked by default unless a manual review workflow records source, date, reviewer, and allowed use.
- `research_needed`, `missing`, and `insufficient_history` are always AI blocked.

## Future Audit Extension Design

Future audit fields can be added without changing provider logic:

```text
valuation_available
valuation_proxy_available
breadth_proxy_available
concentration_proxy_available
crisis_confirmation_sufficient
missing_for_valuation
missing_for_breadth
missing_for_crisis_confirmation
```

Suggested semantics:

- `valuation_available`: true only when at least one real valuation metric has dated official/public-research evidence.
- `valuation_proxy_available`: true when proxy valuation context exists, but it must not satisfy true valuation.
- `breadth_proxy_available`: true when SPY/RSP or related proxy metrics are OK.
- `concentration_proxy_available`: true when QQQ/SPY or SPY/RSP proxy metrics are OK.
- `crisis_confirmation_sufficient`: true only when credit, volatility, breadth/proxy breadth, and macro deterioration gates are all satisfied.
- `missing_for_valuation`: list blocked valuation keys and reasons.
- `missing_for_breadth`: list missing true breadth keys and proxy caveats.
- `missing_for_crisis_confirmation`: list missing crisis-confirmation dimensions.

## Dashboard Integration Roadmap

### Step V1: Proxy breadth derived metrics

Implemented local-only historical derived specs for SPY/RSP/QQQ/HYG/LQD proxy returns and relative returns.
Added no-network tests and audit fields.
Do not add live yfinance calls beyond the existing manual ingest script.

### Step V2: Valuation source research

Research S&P 500 trailing PE, forward PE, CAPE, earnings yield, and Nasdaq 100 valuation sources.
Document source freshness, licensing/redistribution boundary, and whether each can be `public_research` or must remain manual/search-derived.

V2 gate status:

- `docs/valuation_source_research.md` documents candidate sources and blocks provider integration.
- `valuation_available` remains false until a dated valuation metric with source, license boundary, observation date, freshness, and AI-context policy exists.
- `valuation_proxy_available` remains false; SPY/QQQ/RSP returns and proxy breadth are price-only context, not valuation.
- CAPE/Shiller is only a `public_research` candidate for a later phase.

### Step V3: SKEW and tail-risk research

Evaluate CBOE SKEW or similar public tail-risk data.
Keep it optional unless source reliability and freshness rules are clear.

### Step V4: Citation-backed valuation/news layer

If Tavily or another citation layer is later allowed, keep search-derived values blocked until each value has source URL, date, extraction confidence, and review status.

### Step V5: Dashboard integration

Only after audit gates exist, add compact Dashboard rows or drawer-only rows for proxy breadth/concentration.
Keep homepage cards conservative.
Do not add trading advice or convert proxy signals into buy/sell recommendations.

## MVP Exclusions

The following are not for MVP implementation:

- full holdings-level S&P 500 concentration model
- full sector-weight database
- earnings revision model
- analyst estimate aggregation
- intraday breadth or tick-level market internals
- automated search-derived valuation claims without citations
- portfolio action recommendations from valuation or breadth signals
