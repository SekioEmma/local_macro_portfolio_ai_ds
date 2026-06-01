# Daily Workflow

This clean repo keeps only the DS-first analyst memo workflow.

## Commands

Run from the project root:

```powershell
python scripts/run_market_data_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/run_analyst_memo.py
```

Use dry-run mode to validate the prompt package and output writing without calling DeepSeek:

```powershell
python scripts/run_analyst_memo.py --dry-run
```

## Inputs

- `data/holdings/current_holdings.csv` is the local real holdings snapshot and is ignored by Git.
- `data/holdings/current_holdings.example.csv` is placeholder-only sample structure.
- `configs/data_sources.yaml` controls public data provider settings.
- `configs/analyst_memo.yaml` controls DeepSeek analyst memo behavior.

## Outputs

Generated files under `outputs/reports/` and `outputs/analyst_memos/` are local artifacts and ignored by Git. Review them locally, but do not commit real generated reports.

Analyst memo JSON and Markdown can contain prompts, sanitized context, market
summaries, portfolio allocation direction, and model answers. Treat real
`outputs/` files as private local artifacts; do not manually upload or publicly
share them unless they have been reviewed and redacted.

## Boundaries

- No automatic trading.
- No concrete buy/sell instructions.
- No short-term forecasts.
- No API keys in files.
- No qwen/Ollama local model path in this clean repo.
- Do not send `.env`, API keys, raw `data/private/` content, or the full real
  holdings CSV to DeepSeek.
- DeepSeek requests may contain sanitized context, market data summaries,
  asset-class allocation direction and deviation, target-allocation context,
  and DCA-rule context.
- Sanitized context is not fully anonymous: it can still reveal portfolio
  structure, allocation drift, DCA rules, and market-analysis assumptions.
