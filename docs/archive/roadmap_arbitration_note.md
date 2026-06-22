# Roadmap Arbitration Note

## Scope

DF-0 is docs-only roadmap arbitration after D19 v0. It does not implement D19
v1, D15, D16, AI Chat, Tavily/search, endpoints, frontend UI, persistence, live
fetches, or external AI productization.

## Current Execution Sources

The current execution sources are:

- `docs/current_project_state.md`
- `docs/modeling_roadmap.md`
- `docs/short_term_development_plan.md`
- `docs/stage9_3b_one_shot_review.md`
- `docs/stage9_3b_security_closeout.md`
- `docs/d19_historical_validation_v0.md`

`main` remains the stable baseline and should not be touched for current
`app-mvp` work.

## Legacy Documents

`docs/ROADMAP_CURRENT.md` is a historical APP roadmap. It is not the current
execution source and does not authorize DeepSeek Chat productization,
Tavily/search, frontend AI UI, full-account external context, persistence, or
new API endpoints.

Legacy APP notes may remain as product-history context only when clearly marked
legacy, historical, superseded, or not current.

## Resolved Conflicts

- APP roadmap vs modeling/data roadmap: Stage DF is current; the old APP plan is
  legacy.
- Full account context vs Stage 9.3 privacy boundary: external AI context must
  not include holdings line items, account values, position weights, or
  transaction history.
- AI Chat/Tavily vs external AI frozen: Stage 9.3-B-2d completed the internal
  one-shot manual review, and the external AI line remains frozen.
- D15 design vs existing D15 implementation audit: DF-2 should audit the
  existing implementation rather than invent a parallel model.
- D19 v0 registry vs D19 v1 evidence-row integration: D19 v0 is complete as a
  static registry and replay skeleton; DF-1 should integrate existing
  historical validation summaries into D19 replay rows.

## Final Decision

Stage DF begins with DF-0. The next engineering task is DF-1 D19 v1 historical
evidence-row integration. External AI remains frozen.
