# Local Macro Portfolio AI DS

Local Macro Portfolio AI DS is a DS-first personal macro portfolio research assistant. It builds a local market and portfolio data package, renders deterministic daily reports and an LLM context pack, then uses DeepSeek V4 Pro for analyst memo generation.

This project is not an automated trading system. It does not place orders, predict short-term market moves, guarantee returns, or output specific buy/sell instructions.

## Default Workflow

Run from the project root:

```powershell
python scripts/run_market_data_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/run_analyst_memo.py
```

Dry-run the memo package without calling DeepSeek:

```powershell
python scripts/run_analyst_memo.py --dry-run
```

## Environment Variables

API keys must come from environment variables only. Do not write secrets into source files, docs, configs, or committed outputs.

- `DEEPSEEK_API_KEY`
- `FRED_API_KEY`
- `ALPHA_VANTAGE_API_KEY`

## Holdings

Real holdings belong in `data/holdings/current_holdings.csv`, which is ignored by Git. The committed `data/holdings/current_holdings.example.csv` contains generic placeholder rows only.

## Privacy

- `.env` and `.env.*` are ignored.
- `data/holdings/current_holdings.csv` is ignored.
- `data/private/` is ignored.
- generated `outputs/` files are ignored except `.gitkeep`.
- API keys are environment-only.

Local-only data must stay on this machine: API keys, `.env` files, the real
`data/holdings/current_holdings.csv`, anything under `data/private/`, and real
generated files under `outputs/reports/` or `outputs/analyst_memos/`.

DeepSeek is an external API. Analyst memo requests may include the sanitized
context pack, market data summaries, asset-class allocation direction and
deviation, target-allocation context, DCA-rule context, and market judgement
context. They must not include the raw holdings CSV, `.env` or API keys, raw
`data/private/` content, or full generated outputs.

Sanitized does not mean anonymous. Even if absolute account amounts are hidden,
the context can still reveal portfolio structure, asset-class deviations,
target allocation, DCA rules, and the local market-analysis frame. Generated
analyst memo JSON or Markdown can also contain prompts, sanitized context, and
model answers; do not upload or publicly share real `outputs/` artifacts unless
they have been separately reviewed and redacted.

This project is research support only. Requests sent to DeepSeek leave the
local machine, and real investment decisions require human review.

## Legacy Project

The qwen local legacy path is intentionally not included in this clean DS-first repo. To inspect the old local qwen MVP, use the full-history project tag `v6-local-qwen-mvp`.
