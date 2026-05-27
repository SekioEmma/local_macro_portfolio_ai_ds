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

## Legacy Project

The qwen local legacy path is intentionally not included in this clean DS-first repo. To inspect the old local qwen MVP, use the full-history project tag `v6-local-qwen-mvp`.
