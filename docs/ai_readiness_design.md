# AI Readiness Design

## Purpose

Stage 9 creates future memo, report, and chat surfaces over the existing AI
Context Manifest. It is an application layer for reviewing already-audited
evidence and model context. It is not a new financial model, not a data source,
and not permission to call an external model.

Stage 9.0 is the readiness design package. It defines the context contract,
privacy rules, validator expectations, and staged implementation sequence
needed before Stage 9.1, Stage 9.2, Stage 9.3, or Stage 9.4 can proceed.

## Non-Goals

- Do not implement AI Chat.
- Do not implement DeepSeek.
- Do not implement Tavily.
- Do not implement Tauri.
- Do not implement a real LLM adapter.
- Do not implement a search adapter.
- Do not add frontend chat UI.
- Do not add persistent chat storage.
- Do not add agent frameworks or MCP.
- Do not add automatic report saving.
- Do not change D10-D19 or Stage 8 financial model behavior.

## Allowed Context Sources

Stage 9 may consume only the AI Context Manifest and its explicit sections:

- `included_facts`
- `excluded_facts`
- `included_model_outputs`
- `excluded_model_outputs`
- `risk_boundaries`
- `privacy_policy`
- `search_policy`
- `portfolio_context_policy`
- `persistence_policy`

Future Stage 9 surfaces must treat the manifest as the contract boundary. They
must not reconstruct dashboard rows, read provider files directly, or bypass AI
context eligibility flags.

## Forbidden Context Sources

Stage 9 must not read:

- Holdings line items.
- `data/holdings/current_holdings.csv`.
- `data/private/`.
- Raw provider payloads.
- Raw prompts.
- `.env`.
- API keys.
- `outputs/reports` private content.
- SQLite DB files directly.
- Cache payloads.
- Account-level position details.
- Transaction history.

## Privacy Boundary

Stage 9 may use sanitized compact portfolio context only when it is already
present in the AI Context Manifest. It must not expose holdings line items,
account values, position weights, transaction history, or raw account details.
Missing sanitized portfolio context must remain visible as a constraint and must
not be converted into low or high exposure.

## Model Destination Policy

Stage 9.0, Stage 9.1, and Stage 9.2 are local/mock phases. They must not send
content to an external model and must not create external-model output.

Any future Stage 9.3 DeepSeek adapter must be disabled by default, must require
an explicit user-controlled switch, must show a context preview before send,
and must pass response validation before display or persistence.

## Search Policy

Stage 9.0, Stage 9.1, Stage 9.2, and Stage 9.3 do not use Tavily or live search.
Search-derived rows remain excluded unless a future explicit-search phase allows
cited material under a separate policy.

Stage 9.4 Tavily explicit-search beta, if later implemented, may send only the
user's search query. It must not send account, portfolio, holdings, provider
payload, or AI Context Manifest private data. Search failure must not invent
facts.

## Persistence Policy

No Stage 9 phase may automatically save ordinary chat, raw prompts, raw model
responses, raw provider payloads, or private report content by default.

Local deterministic previews may exist in memory or be rendered for user review.
Saving a report or memo requires a later explicit feature, explicit user action,
and validator approval.

## Human Review Policy

All memo, report, and chat-like outputs require human review. Stage 9 output is
research assistance and boundary-preserving explanation, not an action
directive, not an event-odds model, not a return-estimation model, and not a
position-level output.

## Validator Policy

Every future Stage 9 renderer or adapter must run a validator before output is
accepted. The validator must reject forbidden language, action directives,
allocation advice, return estimates, event odds, position-level
recommendations, privacy leakage, uncited search facts, and missing-boundary
notices.

## Memo / Report Boundary

Stage 9 memo and report surfaces may summarize manifest facts, model outputs,
excluded constraints, and risk boundaries. They must preserve interpretation
boundaries and may not upgrade excluded rows into factual support.

They must not output:

- Buy.
- Sell.
- Add position.
- Reduce position.
- Clear position.
- Hedge.
- Rebalance.
- Target allocation.
- Target weight.
- Ideal allocation.
- Expected return.
- Predicted return.
- Market direction probability.
- Crash probability.
- Recession probability.
- Strategy return.
- Trading performance.
- Position-level recommendation.

Safer wording includes:

- Not an action directive.
- Not an event-odds model.
- Not a return-estimation model.
- Not a position-level output.
- Not external-model output in mock/local phases.

## Stage 9 Subphase Sequence

1. Stage 9.0 AI Readiness Design: docs and contracts only; no real AI
   integration.
2. Stage 9.1 Memo Template / Context Contract: deterministic local memo
   templates over AI Context Manifest.
3. Stage 9.2 Mock Chat / Mock Memo: local/mock preview endpoints and
   deterministic renderer.
4. Stage 9.3 DeepSeek adapter: disabled by default and behind an explicit
   user-controlled switch.
5. Stage 9.4 Tavily explicit-search beta: disabled by default and query-only,
   with cited results required.
6. Stage 9.5 Tauri / Desktop Shell: only after backend, frontend, and AI
   surfaces stabilize.
