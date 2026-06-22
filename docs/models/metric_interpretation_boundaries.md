# Metric Interpretation Boundaries

## Purpose

This document records metric-level interpretation boundaries recovered from the
course-paper research. It is documentation only. It does not add new model
logic, Dashboard modules, AI endpoints, or external calls.

## Metric: VIX

### What It Can Support

VIX can support an interpretation of implied-volatility pressure and option
market risk aversion.

### What It Cannot Support

VIX cannot alone confirm credit stress, funding stress, systemic financial
stress, crash probability, recession probability, or future market direction.

### Production Usage

Use VIX as one volatility-pressure evidence row subject to source, freshness,
and AI-context gates.

### AI Memo Language

"VIX is elevated relative to its own history, indicating volatility pressure;
it does not by itself confirm systemic stress."

### Forbidden Wording

Do not call VIX a crash-probability metric or a standalone crisis signal.

## Metric: Equity Drawdown

### What It Can Support

Equity drawdown can support realized equity damage and market-stress context.

### What It Cannot Support

Equity drawdown cannot alone confirm systemic financial stress, future market
direction, recession probability, or expected return.

### Production Usage

Use drawdown as realized equity-damage evidence. It can inform D11/D15/D19
context only when combined with broader evidence and boundaries.

### AI Memo Language

"The drawdown indicates realized equity pressure, while broader credit,
funding, and macro evidence are still needed before escalating the stress
interpretation."

### Forbidden Wording

Do not say a drawdown proves a crash, predicts the next market move, or implies
a trade.

## Metric: Credit Spread

### What It Can Support

Credit spreads can support credit-pressure interpretation. Core HY/IG or
official spread evidence is stronger than ETF proxy spread evidence.

### What It Cannot Support

Credit spreads cannot provide portfolio allocation advice, equity direction,
or a complete macro regime by themselves. Missing HY/IG/core spread evidence
means no confident credit-stress conclusion.

### Production Usage

Use core credit spreads where available. ETF proxy spreads remain auxiliary and
cannot trigger strong labels by themselves.

### AI Memo Language

"Credit spread evidence supports credit-pressure review when sourced and fresh;
proxy-only credit evidence should stay auxiliary."

### Forbidden Wording

Do not convert spread widening into buy/sell/hedge/rebalance instructions.

## Metric: Long-term Rates / Real Yield

### What It Can Support

Long-term rates and real yields can support rates-pressure and discount-rate
pressure interpretation.

### What It Cannot Support

They cannot alone imply financial crisis, recession probability, equity
direction, bond trade signals, or allocation decisions.

### Production Usage

Use rates and real-yield rows as pressure evidence with clear source and
freshness status. DGS30 alone cannot trigger a high rates-pressure label.

### AI Memo Language

"Rates and real yields point to discount-rate pressure, but crisis or systemic
stress interpretation requires confirming evidence from other groups."

### Forbidden Wording

Do not state that a rate level requires a bond/equity trade.

## Metric: External Stress Indices

### What It Can Support

NFCI, STLFSI, OFR FSI, KCFSI, or similar external indices can support
independent reference comparison.

### What It Cannot Support

They cannot replace D10, D11, D15, D19, or project evidence gates. They are not
direct production triggers.

### Production Usage

Use as reference-only context unless separately implemented as dated,
source-badged evidence rows.

### AI Memo Language

"External stress indices can be read as independent context; agreement or
conflict should be documented without overriding the project model."

### Forbidden Wording

Do not say an external index is the project model or an automatic trigger.

## Metric: HYG/LQD or Proxy Spread

### What It Can Support

HYG/LQD-style proxy spread can support auxiliary credit-market proxy context.

### What It Cannot Support

It cannot replace official credit spreads, confirm systemic credit stress, or
trigger strong labels alone.

### Production Usage

Use proxy spread as proxy evidence only, with source badge and boundary text.

### AI Memo Language

"Proxy credit-spread evidence is directionally useful but should not replace
core credit spread inputs."

### Forbidden Wording

Do not call proxy-only spread evidence a definitive credit-stress signal.

## Metric: SPY/RSP or Equity Structure Proxy

### What It Can Support

SPY/RSP or similar proxy pairs can support limited breadth or concentration
context.

### What It Cannot Support

They cannot replace constituent-level breadth, valuation, or earnings data.
They cannot determine a macro regime or systemic stress review by themselves.

### Production Usage

Use as limited proxy context, not as a true-breadth layer.

### AI Memo Language

"Proxy breadth can highlight concentration context, but true breadth and
earnings/valuation evidence remain separate research gaps."

### Forbidden Wording

Do not treat proxy breadth as a complete breadth model.

## Global Forbidden Wording

Avoid the following in public outputs and AI memo language:

- crash probability
- recession probability
- buy
- sell
- hedge
- rebalance
- target allocation
- expected return
- predicted return
- future return
- will rise
- will fall
- guaranteed
