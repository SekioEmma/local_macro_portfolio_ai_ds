# Stage 9.3-B-2d Internal One-shot Manual Invocation Review

Status: completed 2026-06-16.

## Scope

Stage 9.3-B-2d adds an internal, local-only, command-line-only one-shot
DeepSeek review script:

- Not AI Chat.
- Not an HTTP endpoint.
- Not frontend UI.
- Not a persistent report, memo, or chat feature.
- Not automatic provider execution.

The script exists only to manually verify that the real provider path remains
inside the existing manifest-only request builder, request guard, runtime
policy, provider payload contract, transport contract, external response
validator, and external response guard.

## Required Manual Flags

A real provider call is blocked unless all explicit flags are present:

```bash
python scripts/dev_deepseek_one_shot_review.py \
  --live-call \
  --i-understand-this-calls-deepseek \
  --confirm-context-preview
```

Running without flags, or with incomplete flags, prints sanitized summaries and
fails closed before transport is constructed.

## Secret Handling

- The only live-call secret source is process env `DEEPSEEK_API_KEY`.
- `.env` is not read.
- `configs/external_llm.yaml` is not read.
- API keys are not printed.
- Raw request/provider payloads and raw provider responses are not printed or
  saved.

## Data Boundary

The script consumes the AI Context Manifest only. It does not read dashboard raw
responses, holdings files, private data directories, SQLite files, output
artifacts, cache files, or external LLM config files.

It does not send or expose:

- raw question or raw prompt text
- holdings/account/position/transaction data
- Tavily/search results
- raw provider payloads
- local private paths

Missing, research-needed, stale, or otherwise excluded context remains missing
or excluded. DeepSeek output is not a fact layer.

## Output Boundary

Before any possible live call, the script prints only a sanitized context
preview summary:

- included fact count
- included model output count
- excluded context summary
- boundary notices
- provider and mode
- no-persistence and human-review markers
- dangerous permission summary

After a provider response, the script prints only a sanitized result summary:

- provider
- external model called flag
- fake response flag
- validator pass flag
- blocked/privacy finding counts
- content character count
- human-review and no-persistence markers
- short content preview, capped at 800 characters

Content preview is omitted when the validator or external guard reports
forbidden output terms or privacy tokens.

## Manual Run Instruction

Dry-run:

```bash
python scripts/dev_deepseek_one_shot_review.py
```

Manual live run, after setting `DEEPSEEK_API_KEY` in the process environment:

```bash
python scripts/dev_deepseek_one_shot_review.py \
  --live-call \
  --i-understand-this-calls-deepseek \
  --confirm-context-preview
```

Do not commit local outputs, logs, cookies, prompts, provider responses, or
environment files. The Stage 9.3-B-2d tests do not perform live calls.

## Freeze Statement

Stage 9.3-B-2d completes the internal one-shot manual invocation review.
External AI line is now frozen. No AI Chat/product endpoint/frontend UI/
persistence/Tavily/search was added. Next work should return to the core
modeling/data roadmap.

DF-0 roadmap arbitration confirms that any user-facing AI feature requires a
separate explicit approval. The next modeling/data task after DF-0 is D19 v1
historical evidence-row integration.
