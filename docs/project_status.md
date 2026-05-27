# Local Macro Portfolio AI DS - Project Status

## Stage 8.0: Clean DS-first Project

Status: initial clean extraction.

Scope:
- Keep the DeepSeek V4 Pro analyst memo provider.
- Keep deterministic market data checks, daily report generation, LLM context pack generation, and portfolio snapshot generation.
- Keep public/auditable market data package boundaries for rates, inflation, oil, financial conditions, unavailable valuation, unavailable FedWatch, and unavailable market breadth.
- Keep privacy boundaries for local holdings, API keys, private data, and generated outputs.

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
- generated `outputs/` files are ignored and not committed.
- `data/private/` is ignored and not committed.
- The project is not an automated trading system and does not output buy/sell instructions.

Legacy reference:
- The old local qwen MVP is preserved in the full-history project via tag `v6-local-qwen-mvp`.
- The DS-first full-history source is preserved in the original project via tag `v7-ds-first-full-history`.
