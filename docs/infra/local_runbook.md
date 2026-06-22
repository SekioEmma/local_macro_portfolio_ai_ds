# Local Runbook

## Purpose

This runbook describes local checks for the `app-mvp` macro risk research
workbench. It is intentionally local-first and read-only unless a task explicitly
allows writes.

## Preflight

Run these commands before editing:

```bash
git fetch origin
git status --short --untracked-files=all
git branch -vv
git log --oneline -12
```

Continue only when:

- The current branch is `app-mvp`.
- The working tree is clean or all dirty files are explained and allowed by the task.
- The local branch is not ahead of or behind `origin/app-mvp`.
- `git status` does not show `.env`, SQLite, outputs, cache, holdings, private data,
  API keys, or raw provider data.

## Validation Commands

Use the commands that exist in this repo. If a future task is uncertain about a
command, inspect repo scripts and package scripts first instead of inventing a
new command.

Core validation:

```bash
python scripts/benchmark_dashboard_pipeline.py
python scripts/audit_data_pipeline_coverage.py
python -m pytest -q
```

Frontend validation:

```bash
cd app_frontend && npm run typecheck
cd app_frontend && npm run build
```

Boundary validation:

```bash
python scripts/dev_check_validator_boundaries.py
git diff --check
git status --short --untracked-files=all
```

Dry-run ingestion checks:

```bash
python scripts/ingest_liquidity_funding_history.py --dry-run
python scripts/ingest_core_risk_history.py --dry-run
python scripts/ingest_yfinance_history.py --dry-run
python scripts/ingest_market_history_from_dashboard.py --dry-run
python scripts/ingest_official_energy_history.py --dry-run
python scripts/ingest_official_ppifis_history.py --dry-run
python scripts/ingest_official_labor_history.py --dry-run
```

## Failure Reporting

If any command fails:

- Report the exact command.
- Report the exact error or failing summary.
- Do not fake success.
- Do not continue into broader edits until the failure is understood or the user
  explicitly accepts the risk.

## Privacy Rules

Do not read or edit:

- `.env*`
- `configs/external_llm.yaml`
- `data/holdings/`
- `data/private/`
- `data/app_state/*.sqlite3`
- `data/market_history/*.sqlite3`
- `data/cache/`
- `outputs/`

Do not commit SQLite DB files, cache files, output files, holdings, private data,
environment files, API keys, or raw provider payloads.

