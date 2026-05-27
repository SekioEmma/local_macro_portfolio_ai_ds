# Local Macro Portfolio AI DS - Project Status

## Stage 8.2: DS-first Observation and Validator Repair

Status: clean extraction complete; Stage 8.2 observation is active.

Scope:
- Keep the DeepSeek V4 Pro analyst memo provider.
- Keep deterministic market data checks, daily report generation, LLM context pack generation, and portfolio snapshot generation.
- Keep public/auditable market data package boundaries for rates, inflation, oil, financial conditions, unavailable valuation, unavailable FedWatch, and unavailable market breadth.
- Keep privacy boundaries for local holdings, API keys, private data, and generated outputs.

Current 8.2 focus:
- Real holdings are configured only in the local ignored holdings file; no private holdings content belongs in Git.
- DeepSeek analyst memo outputs remain local ignored artifacts under `outputs/`.
- The memo validator is being tuned for evidence-table boundary handling without weakening hard flags for fabricated market data.
- Continue observation with a small number of real memo summaries; only repair code for fact errors, privacy risks, hard flags, or workflow defects.

Removed from this clean repo:
- local qwen/Ollama Q&A entrypoint
- qwen eval scripts and eval question configs
- qwen prompt builder, fallback, guardrails, intent router, and local LLM client
- conversation distillation legacy docs
- real generated outputs
- real holdings files
- private data directory

Current boundaries:
- API keys are environment-only.
- `data/holdings/current_holdings.csv` is ignored and not committed.
- generated `outputs/` files are ignored and not committed, except placeholder `.gitkeep` files.
- `data/private/` is ignored and not committed.
- The project is not an automated trading system and does not output buy/sell instructions.

Legacy reference:
- The old local qwen MVP is preserved in the full-history project via tag `v6-local-qwen-mvp`.
- The DS-first full-history source is preserved in the original project via tag `v7-ds-first-full-history`.
