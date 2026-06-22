# Valuation Source Research Gates

This document is a research gate, not a provider integration. It does not add valuation data, does not call PE/CAPE/earnings providers, and does not allow price-only proxies to enter valuation or AI factual context as valuation facts.

| candidate_metric_key | candidate_source | source_url_or_source_name | source_type | update_frequency | observation_date_available? | redistribution/licensing concern | can_enter_dashboard? | can_enter_ai_factual_context? | implementation_complexity | risk_level | recommendation | boundary_text |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sp500_trailing_pe` | S&P Dow Jones Indices, exchange/public research, or reviewed manual/citation layer | S&P 500 fundamentals source to be selected | `research_needed` | Daily/monthly depending on source | Required but not selected | Likely redistribution constraints | No | No | Medium | High | `keep_research_needed` | Do not derive PE from S&P 500 price-only data; needs dated earnings denominator and source license. |
| `sp500_forward_pe` | FactSet, S&P Capital IQ, Bloomberg, Reuters, or licensed consensus source | Provider/license source to be selected | `research_needed` | Weekly/monthly depending on provider | Required but not selected | High, likely licensed | No | No | High | High | `block` | Forward PE needs analyst consensus; keep blocked without licensed or citation-reviewed source. |
| `cape_shiller_pe` | Robert Shiller public research dataset | Online Data - Robert Shiller | `public_research` | Monthly, after data file update | Candidate likely yes, must verify per file | Redistribution and attribution boundary must be documented | No in this round | No in this round | Medium | Medium | `implement_later` | CAPE is a long-horizon valuation metric, not a short-term buy/sell or crash confirmation signal. |
| `earnings_yield` | Derived only from verified PE or earnings denominator | Depends on selected PE/earnings source | `research_needed` | Inherits source | Required | Inherits source | No | No | Medium | High | `block` | Do not compute earnings yield until PE or earnings denominator is verified. |
| `equity_risk_premium_proxy` | Derived only after earnings yield plus Treasury/real-yield basis is selected | Internal formula plus sourced inputs | `research_needed` | Inherits inputs | Required | Inherits sources | No | No | Medium | High | `block` | ERP proxy is blocked until earnings yield口径 and rate basis are explicit. |
| `nasdaq100_valuation_proxy` | Nasdaq/QQQ fundamentals provider or public research/citation layer | Source to be selected | `research_needed` | Daily/monthly depending on source | Required but not selected | Likely licensed or redistribution-limited | No | No | Medium | High | `keep_research_needed` | QQQ or Nasdaq 100 price return is not valuation. |
| `earnings_revision` | FactSet/IBES/Bloomberg/Reuters or reviewed search-derived citation layer | Provider/source to be selected | `research_needed` | Weekly/monthly | Required but not selected | High, likely licensed | No | No | High | High | `block` | Earnings revision/EPS growth requires provider or citation layer; no raw search-derived value may be used directly. |
| `eps_growth` | Analyst consensus or index earnings source | Provider/source to be selected | `research_needed` | Quarterly/monthly | Required but not selected | High, likely licensed | No | No | High | High | `block` | EPS growth must not be inferred from price returns or broad macro data. |
| `sp500_top10_weight` | S&P Dow Jones Indices, SPY holdings, or reviewed public research | Source to be selected | `research_needed` | Daily/monthly depending on source | Required but not selected | Holdings redistribution constraints likely | No | No | Medium | Medium | `keep_research_needed` | ETF/top-holdings data cannot silently become official S&P 500 concentration. |

## Conservative Conclusions

- PE and forward PE must not be derived from price-only data.
- Earnings yield must not be derived until PE or earnings denominator is verified.
- ERP proxy must not be derived until the earnings-yield口径 is verified.
- Forward PE, earnings revision, and EPS growth likely require a licensed provider or a reviewed citation layer; default status is blocked.
- Shiller CAPE is a public_research candidate, but update frequency, field口径, disclaimer, and redistribution boundary must be verified before any provider or dashboard integration.
- Shiller CAPE must not be used for short-term trading advice.
- Valuation metrics must not become crash confirmation signals.

## Gate Design

`valuation_available` may be true only after a dated valuation metric with source, observation date, freshness, license boundary, and AI-context rule is implemented. This round keeps it false.

`valuation_public_research_candidate_available` may be true because CAPE/Shiller source research exists in this document. It does not mean valuation data is available.

`valuation_proxy_available` remains false. SPY/QQQ/RSP returns and breadth/concentration proxies are price-only context, not valuation.

Blocked metrics for audit:

- `sp500_trailing_pe`
- `sp500_forward_pe`
- `cape_shiller_pe`
- `earnings_yield`
- `equity_risk_premium_proxy`
- `nasdaq100_valuation_proxy`
- `earnings_revision`
- `eps_growth`
- `sp500_top10_weight`

Recommended next step: design a manual/citation-reviewed valuation context gate with explicit source URL/name, observation date, reviewer/status, redistribution note, and `can_enter_ai_factual_context=false` by default until review rules are implemented.
