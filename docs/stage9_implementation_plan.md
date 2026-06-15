# Stage 9 Implementation Plan

## Stage 9.0 AI Readiness Design

Status: current task.

- Create docs and contracts only.
- Define AI Context Manifest consumption rules.
- Define memo/report context rules.
- Define staged implementation gates.
- Do not implement real AI integration.
- Do not change Python or TypeScript production behavior.

## Stage 9.1 Memo Template / Context Contract

- Build deterministic memo templates only.
- Render locally.
- Consume AI Context Manifest only.
- Preserve included/excluded context boundaries.
- Add validator checks before display.
- No external model call.
- No persistent chat.
- No Tavily.
- No holdings exposure.

## Stage 9.2 Mock Chat / Mock Memo

- Add mock/local preview endpoints only.
- Use a deterministic renderer.
- Show manifest-derived context preview.
- Run validator before output is accepted.
- No DeepSeek.
- No Tavily.
- No network.
- No raw prompt persistence.
- No holdings exposure.
- No automatic report saving.

## Stage 9.3 DeepSeek Adapter Behind Explicit User-Controlled Switch

- Start only after Stage 9.1 and Stage 9.2 pass.
- Keep adapter disabled by default.
- Require an explicit UI or settings switch.
- Show context preview before send.
- Show cost and model metadata.
- Send only approved AI Context Manifest material.
- Run validator after response.
- Do not save ordinary chat by default.
- Do not persist raw prompts.
- Do not include holdings line items.
- Do not include account values, position weights, or transaction history.

## Stage 9.4 Tavily Explicit-Search Beta

- Keep disabled by default.
- Send only the user's search query.
- Do not send account context.
- Do not send portfolio context.
- Do not send holdings or transaction data.
- Require cited results.
- Treat search failure as missing context.
- Do not invent facts after search failure.
- Do not keep a long-term search cache by default.

## Stage 9.5 Tauri / Desktop Shell

- Start only after backend, frontend, and AI surfaces stabilize.
- Do not add hidden background calls.
- Do not add automatic provider refresh.
- Do not add account editing unless a later phase explicitly permits it.
- Preserve local-first, privacy-first, fail-closed behavior.

## Dependency Gates

- M7/M8 are not blockers for Stage 9 preparation.
- M7/M8 should be considered before complex Stage 9 implementation.
- M12 AI Context Manifest Contract Hardening should remain active during all
  Stage 9 work.
- Stage R Course Paper Research Recovery remains optional docs/research work and
  must not enter production model logic.

## Global Stage 9 Boundaries

- Stage 9 is an application surface over AI Context Manifest.
- Stage 9 is not a new financial model.
- Stage 9 is not a new data source.
- Stage 9 must not change D10-D19 or Stage 8 model semantics.
- Stage 9 must not broaden AI context eligibility.
- Stage 9 must not bypass existing AI context gates.
- Stage 9 must not output action directives, allocation advice, return
  estimates, event odds, or position-level recommendations.
