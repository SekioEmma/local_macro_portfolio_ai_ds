# Audit Pipeline Architecture

## CLI Entry Point

The public audit command remains:

```bash
python scripts/audit_data_pipeline_coverage.py
```

That script still owns argument parsing, report serialization, Markdown output,
and `build_coverage_audit(...)` orchestration. The JSON contract is unchanged:
top-level audit keys, D10/D11/D13/D14 section keys, historical-store keys, and
AI manifest privacy keys are preserved.

## M5 Module Layout

M5 split section helpers out of the CLI file without changing audit semantics:

- `scripts/audit_sections/common.py` contains shared constants and row helpers.
- `scripts/audit_sections/module_audits.py` contains module-level audit sections,
  including D10, D11, D13, D14, proxy breadth, market stress, valuation, and
  portfolio compact checks.
- `scripts/audit_sections/history_audits.py` contains market-history,
  historical-derived, energy, liquidity/funding history, core-risk history, and
  yfinance history audits.
- `scripts/audit_sections/manifest_audit.py` contains AI manifest audit and
  privacy flag checks.

The split is intentionally import-local to `scripts/` to keep direct CLI
execution stable on Windows and avoid package-path churn.

## Boundaries

M5 does not change D10 scoring, D11 systemic review conditions, D13 percentile
or z-score computation, D14 liquidity/funding rules, D12 manifest privacy
policy, dashboard API behavior, benchmark fields, provider behavior, or any
financial interpretation boundary.

The audit still reads existing local reports and local history stores only. It
does not introduce live fetches, database writes, DeepSeek, Tavily, Tauri,
machine learning, account editing, trading instructions, crash probability, or
recession probability.

## Future Work

M5b could add section-level timing around the extracted audit helpers so
benchmarking can distinguish orchestration cost from individual audit-section
cost.

M6 could clean frontend labels and TypeScript types after the audit structure
has stabilized, while keeping the same fact-layer and privacy boundaries.
