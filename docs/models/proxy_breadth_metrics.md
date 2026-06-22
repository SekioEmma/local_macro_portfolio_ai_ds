# Proxy Breadth Metrics

This document describes the V1 proxy breadth and concentration metrics.
They are local-only derived metrics built from existing `market_history` observations.
They do not call yfinance live, do not read raw yfinance responses, and do not create official market breadth or valuation evidence.

## Module

Dashboard and Evidence Table rows use:

```text
breadth_concentration_proxy
```

The module is a proxy evidence surface.
It is not a true market breadth module and it is not a valuation module.

## Metrics

| Metric | Dependencies | Calculation |
| --- | --- | --- |
| `spy_proxy_30d_return` | `spy_proxy` | 30D period return |
| `spy_proxy_60d_return` | `spy_proxy` | 60D period return |
| `rsp_proxy_30d_return` | `rsp_proxy` | 30D period return |
| `rsp_proxy_60d_return` | `rsp_proxy` | 60D period return |
| `qqq_proxy_30d_return` | `qqq_proxy` | 30D period return |
| `qqq_proxy_60d_return` | `qqq_proxy` | 60D period return |
| `spy_vs_rsp_30d` | `spy_proxy`, `rsp_proxy` | SPY 30D return minus RSP 30D return |
| `spy_vs_rsp_60d` | `spy_proxy`, `rsp_proxy` | SPY 60D return minus RSP 60D return |
| `qqq_vs_spy_30d` | `qqq_proxy`, `spy_proxy` | QQQ 30D return minus SPY 30D return |
| `qqq_vs_spy_60d` | `qqq_proxy`, `spy_proxy` | QQQ 60D return minus SPY 60D return |
| `hyg_vs_lqd_30d` | `hyg_proxy`, `lqd_proxy` | HYG 30D return minus LQD 30D return |
| `hyg_vs_lqd_60d` | `hyg_proxy`, `lqd_proxy` | HYG 60D return minus LQD 60D return |

## Data Lineage

Rows are surfaced only when existing local observations are sufficient.

- `source=local_market_history`
- `source_badge=derived`
- `freshness_status=historical`
- dependency observations must have `source_badge=proxy`
- underlying provider can be yfinance only through stored compact observations

The derived rows must not be marked as `official`.

## AI Context Boundary

`ai_context_allowed` may be true only when:

- dependency observations exist
- source/date/freshness metadata are complete
- the interpretation hint states the yfinance ETF proxy boundary
- the row is not treated as official breadth, valuation, or crash confirmation

If local history is missing or incomplete, rows stay `insufficient_history` and AI blocked.

## Audit Fields

`scripts/audit_data_pipeline_coverage.py` includes a `proxy_breadth` block:

- `breadth_proxy_available`
- `breadth_proxy_metric_count`
- `breadth_proxy_ok_count`
- `breadth_proxy_insufficient_history_count`
- `concentration_proxy_available`
- `credit_proxy_available`
- `proxy_metrics_ai_context_allowed_count`

These fields report proxy evidence only.
They do not satisfy true valuation, true breadth, or systemic-crisis confirmation.
