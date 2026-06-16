# Financial Market Pressure Clustering Research Note

## 1. Scope

This note recovers method and boundary value from the course paper research on
U.S. macro-financial pressure state recognition using historical percentiles
and clustering.

It is a research and method note only. It is not a production model, not a
Dashboard module, not an AI Chat feature, and not an external-provider workflow.
It supports future D13, D15, D19, and Stage 9 memo/report language by clarifying
what can be reused and what must remain outside production logic.

## 2. Research Question

The paper question is: can public macro-financial variables help identify
different historical U.S. financial pressure states?

The useful project framing is historical interpretation, not prediction. The
research compares pressure structures across historical samples, such as rates
pressure, credit pressure, implied-volatility pressure, and realized equity
drawdown pressure. It does not estimate future crash odds, recession odds,
asset returns, or portfolio actions.

## 3. Variables

### Rates / Real Yield

Financial meaning: long-term Treasury yields, the 30-year rate, and real-yield
measures can describe discount-rate pressure and policy-rate transmission.

Project relevance: these variables can inform D13 percentile methodology and
D15 rates-pressure evidence review.

Interpretation boundary: rates pressure alone does not prove systemic crisis,
credit impairment, equity direction, or recession probability.

Production evidence layer: eligible when sourced, dated, fresh enough, and
covered by existing evidence-row gates.

### Credit Spread

Financial meaning: high-yield, investment-grade, BAA/Treasury, or comparable
spread measures can describe compensation demanded for credit risk.

Project relevance: credit spread is stronger evidence for credit pressure than
equity-volatility proxies. ETF proxy spreads can help only as auxiliary proxy
evidence.

Interpretation boundary: missing HY/IG/core spread evidence means no confident
credit-stress conclusion. Proxy-only evidence cannot trigger a strong label.

Production evidence layer: eligible only when source, freshness, and proxy
boundaries are visible.

### VIX / Implied Volatility

Financial meaning: VIX captures options-implied equity volatility pressure.

Project relevance: useful for D13 pressure percentile examples and D15
volatility/equity-damage context.

Interpretation boundary: VIX is not crash probability. VIX alone cannot confirm
credit stress, funding stress, or systemic financial stress.

Production evidence layer: eligible as volatility pressure evidence, not as a
standalone systemic trigger.

### Equity Drawdown

Financial meaning: S&P 500 or broad-equity drawdown captures realized equity
damage from recent peaks.

Project relevance: drawdown can help separate ordinary pullbacks from broader
pressure episodes in D11, D15, and D19 notes.

Interpretation boundary: equity drawdown alone cannot confirm systemic
financial stress, future market direction, or return expectations.

Production evidence layer: eligible as realized equity-damage evidence with
current project gates.

### External Stress Index Comparison

Financial meaning: NFCI, STLFSI, OFR FSI, KCFSI, or similar indices aggregate
market stress signals from external methodologies.

Project relevance: useful as independent reference layers for D19 event notes
and research interpretation.

Interpretation boundary: external indices do not replace project D10, D11, or
D15 models. Agreement can strengthen historical interpretation; disagreement
should become conflict context rather than an automatic correction.

Production evidence layer: reference-only unless separately implemented through
dated, licensed, source-badged evidence rows.

## 4. Percentile Transformation

Percentile means historical relative position within a defined sample. It is
not probability. A pressure percentile says that a value is high or low relative
to its own history; it does not say a crash, recession, or market move is more
or less likely by a quantified amount.

Full-sample percentiles are appropriate for coursework and historical
explanation because the whole sample is known after the fact. Production D13
should prefer rolling, expanding, or otherwise as-of-safe percentile
construction so future data cannot leak into past interpretation.

Different indicators must be normalized to a pressure-up scale. For example,
higher VIX and wider credit spreads generally mean higher pressure, while other
series may need sign or distance transformations before percentiles are
compared.

Insufficient history must remain `insufficient_history`. Missing, stale, or
research-needed inputs cannot be filled by AI or by clustering.

## 5. Clustering Method

K-means in the paper is useful for historical structure recognition. A cluster
label is a historical archetype, not a real-time regime classifier.

Cluster centers can help describe combinations of pressure, such as high rates
with moderate volatility or high volatility with equity drawdown. They should
not become Dashboard labels, production triggers, probabilities, or portfolio
actions.

Cluster boundaries depend on sample period, variables, transformations,
standardization, and the selected cluster count. Robustness tools such as PCA
visualization, silhouette review, gap statistic, PAM, or hierarchical clustering
can support research interpretation, but they do not convert the result into a
production classifier.

## 6. Historical Archetypes

The paper can inform D15 label design only at the level of historical
archetypes:

- `low_pressure` / `stable_condition`
- `rates_pressure`
- `volatility_equity_drawdown_pressure`
- `credit_volatility_joint_pressure`
- `mixed_or_transition`

These are not final production labels from the paper. They are vocabulary and
event-note references that may help D15 and D19 describe historical pressure
patterns.

## 7. External Stress Index Comparison

External stress indices are independent reference layers. They can help explain
whether a clustered period resembles broader market-stress measures, but they
do not replace the project model.

When an external index and paper cluster interpretation agree, the project can
record that agreement as historical context. When they disagree, the project
should record a conflict or interpretation note instead of forcing D10, D11, or
D15 to conform.

## 8. Relevance to Project Modules

### D13

D13 can reuse percentile methodology, pressure-up normalization language,
lookback-window discipline, proxy caveats, and `insufficient_history` handling.

### D15

D15 can reuse historical archetype vocabulary as design context. It must not
reuse K-means as a production classifier.

### D19

D19 can reuse event windows, cluster-period descriptions, and external-index
comparison notes as historical validation context. It must not treat them as
prediction backtests.

### Stage 9 AI Memo

Stage 9 memo/report surfaces can reuse boundary sentences that distinguish
historical pressure interpretation from forecasts, probabilities, and actions.

## 9. Non-transferable Parts

The following are not transferable into production logic:

- K-means production model
- GMM production model
- cluster probability
- cluster-to-action mapping
- cluster-to-portfolio mapping
- full-sample percentile as live D13
- cluster dashboard module
- trading instruction
- crash probability
- recession probability

## 10. Final Recovery Decision

The paper results are recovered as research note material, methodology
language, D19 event-note context, and AI memo boundary templates. They do not
enter the production model as clustering logic, live classification, dashboard
modules, trading signals, or probability outputs.
