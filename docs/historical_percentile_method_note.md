# Historical Percentile Method Note

## Purpose

This note converts the course-paper percentile method into project boundary
language for D13 historical percentile metrics and related memo/report text. It
is documentation only and does not change production code.

## What Percentile Means

A percentile is a historical relative position. It describes where the current
or observed value sits within a documented historical sample for the same
metric or transformed pressure series.

Reusable language:

> 分位数表示该指标在自身历史样本中的相对位置，不表示事件发生概率。

## What Percentile Does Not Mean

A percentile is not probability. A high pressure percentile is not crash
probability, recession probability, market-direction probability, expected
return, or trading confidence.

Reusable language:

> 高分位说明压力水平处于历史偏高区间，但不等于危机预测。

## Direction Normalization

Indicators must be mapped to a consistent pressure-up scale before their
percentiles are compared. VIX and credit spreads usually rise with pressure.
Other metrics may require sign changes, distance-to-threshold transforms, or
explicit interpretation boundaries.

Direction choices must be documented. A mixed set of raw directions can create
misleading percentile summaries.

## Full-sample vs Rolling vs Expanding

Full-sample percentile is research-only because it uses the whole sample after
the fact. It is useful for course-paper historical interpretation and
archetype discovery.

Production D13 should use rolling, expanding, or otherwise as-of-safe
percentiles. The lookback window, minimum observation count, and data
availability constraints must remain visible.

## Production D13 Rule

Production D13 percentile rows should:

- document lookback window and observation count
- use pressure-up direction normalization
- expose source, freshness, and history-quality status
- fail closed to `insufficient_history` when history is inadequate
- avoid converting percentile bands into event odds

## Proxy and Insufficient History Handling

Proxy percentile remains proxy evidence. It cannot replace official or core
inputs without explicit source and boundary documentation.

Reusable language:

> proxy 指标只能作为辅助证据，不能替代官方或核心输入。

`insufficient_history` is neither low risk nor high risk. It only means that
the local historical sample is not sufficient for the requested transformation.

Reusable language:

> insufficient_history 不是低风险，也不是高风险，只表示历史样本不足。

## AI Context Boundary Language

AI memo/report surfaces may say that a metric is historically high or low
relative to its own sample. They must also preserve missingness, proxy status,
and interpretation boundaries.

Stale, missing, research-needed, or insufficient-history facts cannot be filled
by AI. AI output is not a fact layer.

## Reliability And Divergence Metadata

DF-4 adds explanatory `reliability_band` and `divergence_band` metadata to
each D13 row.

- `reliability_band` reflects data/method quality (history length, source
  badge, method availability, divergence). It is not probability.
- `divergence_band` flags disagreement among percentile, z-score, and robust
  z-score. It is not market direction.
- Material divergence should be explained as method disagreement, not
  converted into a probability, allocation directive, or trade.

The metadata cannot relax existing AI context eligibility or promote proxy /
insufficient rows into hard triggers.

## Forbidden Interpretations

Do not interpret percentile, reliability, or divergence as:

- crash probability
- recession probability
- market-direction probability
- buy/sell/hedge/rebalance signal
- target allocation
- expected, predicted, or future return
- real-time cluster or regime probability
- proof of systemic stress from one metric alone
