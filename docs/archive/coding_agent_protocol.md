# Coding Agent Protocol

## Required Preflight

Before editing, run:

```bash
git fetch origin
git status --short --untracked-files=all
git branch -vv
git log --oneline -12
```

Report the result before changing files.

## Stop Conditions

Stop immediately when:

- The current branch is not `app-mvp`.
- The working tree has unexplained dirty or untracked files.
- The local branch is ahead of or behind `origin/app-mvp`.
- `git status` shows `.env`, SQLite, outputs, cache, holdings, private data,
  API keys, or raw provider data.
- The task asks for files outside the allowed scope.
- A required validation command fails and the failure is not understood.

## Privacy Red Lines

Never read, edit, stage, or commit:

- `.env*`
- `configs/external_llm.yaml`
- `data/holdings/`
- `data/private/`
- `data/app_state/*.sqlite3`
- `data/market_history/*.sqlite3`
- `data/cache/`
- `outputs/`

Never introduce DeepSeek, Tavily, Tauri, account editing, auto trading,
portfolio optimization, hidden provider calls, raw provider payload exposure, or
AI-filled missing data unless a future task explicitly redefines the scope.

## Allowed And Forbidden Files

For Stage 0 documentation governance, allowed files are only:

- `docs/current_project_state.md`
- `docs/local_runbook.md`
- `docs/coding_agent_protocol.md`
- `docs/short_term_development_plan.md`
- `docs/modeling_roadmap.md`

Do not edit Python, TypeScript, tests, configs, package files, lock files, data,
outputs, cache, SQLite, holdings, or env files during Stage 0.

## Finance And Math Decision Window

Ask the main/finance/math decision owner before:

- Adding a new financial label, threshold, score, weighting, or trigger.
- Changing D10/D11/D13/D14/D14b interpretation boundaries.
- Treating proxy, search-derived, research-needed, stale, missing, or
  insufficient-history rows as official evidence.
- Introducing valuation, earnings, true breadth, scenario, or macro regime logic.
- Adding probability language, trade action language, asset direction certainty,
  or expected-return language.

## Final Report Format

Final reports should include:

- Changed files.
- Summary.
- Tests run.
- Benchmark/audit result.
- Privacy check.
- Remaining risks.
- Commit message suggestion.

Do not commit or push unless explicitly asked.

