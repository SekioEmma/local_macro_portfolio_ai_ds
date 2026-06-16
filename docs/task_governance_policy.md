# Task Governance Policy

## Purpose

Reduce ceremony for low-risk work while preserving strict boundaries for
model, security, and product changes.

Without this policy, every task tends to inherit the heaviest validation and
documentation pattern. That made sense when the project was establishing
boundaries. It is now a real cost.

Each task should pick the lowest level that fully covers its actual risk.

## L1 Micro-fix

Examples:

- typo
- doc link
- test helper comment
- small formatting
- local test fixture cleanup with no production behavior change
- whitespace, import-order, or trivial rename inside a private helper

Allowed validation:

- targeted test if applicable
- `git diff --check`
- `git status --short --untracked-files=all`

L1 does not require governance doc updates unless the current route changes.
L1 does not require a closeout doc. A clear commit message is enough.

## L2 Docs / Audit / Metadata-only

Examples:

- docs-only audit (e.g. DF-3 D17/D18 audit pattern)
- new closeout doc
- INDEX update
- roadmap reconciliation
- test runtime hotfix docs
- governance policy edits
- adding explanatory metadata fields with no behavior or contract change
- targeted test additions that exercise existing behavior

Validation:

- `git diff --check`
- `git status --short --untracked-files=all`
- relevant targeted tests if tests changed
- `python scripts/dev_check_validator_boundaries.py` if any boundary doc or
  forbidden-language source changed

L2 updates governance docs only when the current route, completed stage, or
public contract actually changes.

## L3 Boundary-touching Production Change

Examples:

- D10 / D11 / D13 / D14 / D15 / D16 / D17 / D18 / D19 production model code
- AI Context Manifest eligibility rules
- source gates and badge handling
- trigger eligibility cascades
- public output keys / model registry / golden contract changes
- new metadata fields visible to downstream models or AI context
- evidence pipeline order changes

Validation:

- targeted tests for the changed module
- full pytest (`PYTHONIOENCODING=utf-8 python -m pytest -q`)
- `python scripts/benchmark_dashboard_pipeline.py`
- `python scripts/audit_data_pipeline_coverage.py`
- `python scripts/run_historical_validation.py --format text` if D19 or
  historical replay is touched
- `python scripts/dev_check_validator_boundaries.py`
- `git diff --check`
- `git status --short --untracked-files=all`

L3 updates governance docs (current state, modeling roadmap or short-term
plan, and a closeout doc) when a stage completes or a public contract
changes.

## L4 Product Surface / External AI / Privacy-Sensitive Change

Examples:

- new API endpoint
- frontend UI changes that touch the AI surface or holdings rendering
- DeepSeek / external AI integration
- Tavily / search productization
- persistent chat / memo / report storage
- holdings, account, or position-level context expansion
- live provider fetch or live write
- anything that could expose private data or change the external boundary

Requires explicit user approval before implementation begins.

Validation:

- full backend test suite
- frontend `typecheck` and `build` if the frontend changed
- security closeout tests for the affected boundary
- route surface tests
- privacy and forbidden-output tests
- documented closeout doc summarizing routes, persistence, and
  forbidden-surface scans

## Naming Policy

Future task names and commit messages prefer human-readable names.

Good:

- `Speed up DB-backed test fixtures`
- `Add project index`
- `Optimize pipeline row conversion`
- `Refine D16 scenario explanations`

Avoid deep numbering in commit messages:

- `DF-4d`
- `S2b`
- `M8-C`
- `Stage 9.3-B-2e`

Stage IDs may remain in `docs/INDEX.md`, `docs/short_term_development_plan.md`,
`docs/modeling_roadmap.md`, and stage closeout docs for historical mapping,
but not every commit needs a nested stage code. The commit message should be
readable on its own three months later.

## Governance Update Policy

Do not update three governance docs for every L1 task.

Update governance docs only when at least one of these is true:

- the current route changes
- a stage completes
- a public contract changes (model registry, golden contract, AI context
  schema, forbidden language policy)
- the external or product boundary changes

When governance docs do change, the source of truth ordering is:

1. `docs/INDEX.md` — navigation map and current orientation
2. `docs/short_term_development_plan.md` — immediate route and next task
3. `docs/current_project_state.md` — detailed project state and baseline
4. `docs/modeling_roadmap.md` — modeling-history narrative and boundaries

If these disagree on the immediate route,
`docs/short_term_development_plan.md` wins for "what to do next".
`docs/modeling_roadmap.md` keeps the long-form modeling history and module
boundaries but should not be read as a to-do list.
