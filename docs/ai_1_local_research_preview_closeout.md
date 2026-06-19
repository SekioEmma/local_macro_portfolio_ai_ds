# AI-1 Local Controlled Research Preview Closeout

## Scope

AI-1 completes a local, deterministic research-preview layer over the existing
AI Context Manifest. It adds:

- a full context catalogue for audit;
- mode-aware selected prompt context;
- six controlled answer modes and three detail levels;
- seven-section Chinese research output;
- local language, privacy, and financial-semantic validation;
- read-only research and prompt preview APIs;
- a read-only frontend workbench with catalogue, research, and prompt views.

AI-1 does not call an external model or search service. It does not persist
questions, prompt text, generated answers, or chat history. It does not broaden
AI Context Manifest eligibility, source-gate semantics, or financial-model
semantics.

## API Contract

### `POST /api/ai/research-preview`

Request fields:

| Field | Type | Default | Contract |
|---|---|---:|---|
| `answer_mode` | enum | `risk_review` | One of the six controlled answer modes. |
| `detail_level` | enum | `standard` | `brief`, `standard`, or `deep`. |

Extra request fields are rejected. The endpoint does not accept a free-form
question.

Response fields:

| Field | Type | Meaning |
|---|---|---|
| `mode` | string | Always `local_controlled_research_preview`. |
| `answer_mode` | enum | Effective controlled answer mode. |
| `legacy_memo_type` | string | Compatibility mapping for the legacy memo/report renderer. |
| `detail_level` | enum | Effective detail level. |
| `title` | string | Chinese mode title. |
| `answer_preview` | string | Deterministic seven-section rendered answer; empty when blocked. |
| `research_sections` | array | Structured seven-section output; empty when blocked. |
| `selected_prompt_context` | object | Mode-aware selected cards, aggregate constraints, prompt text, and selection notes. |
| `prompt_budget` | object | Local card, character, and estimated-token budget result. |
| `context_used_summary` | object | Included/excluded fact and model-output counts. |
| `privacy_summary` | object | Manifest-only, no-private-input, no-external-call, no-search, no-save flags. |
| `validator_result` | object | Legacy forbidden-language and privacy validator result. |
| `semantic_validator_result` | object | Structured financial-semantic findings and severity. |
| `not_sent_to_external_model` | boolean | Always `true`. |
| `human_review_required` | boolean | Always `true`. |
| `interpretation_boundary` | string | Fixed local research boundary. |

### `POST /api/ai/prompt-preview`

Request fields are identical to `/api/ai/research-preview`; extra fields are
rejected.

Response fields:

| Field | Type | Meaning |
|---|---|---|
| `mode` | string | Always `local_prompt_preview`. |
| `status` | enum | `ready` or `not_ready`. |
| `answer_mode` | enum | Effective controlled answer mode. |
| `legacy_memo_type` | string | Compatibility mapping. |
| `detail_level` | enum | Effective detail level. |
| `system_boundary` | string | Fixed server-owned safety boundary. |
| `task_instruction` | string | Fixed mode-specific task instruction. |
| `selected_prompt_context` | object | Selected cards and aggregate P4 constraints. |
| `output_contract` | array | Required output structure and financial boundaries. |
| `preflight_checklist` | array | Local-only, privacy, search, persistence, and review checks. |
| `prompt_budget` | object | Local prompt budget result. |
| `prompt_text` | string | Assembled local prompt preview; empty when blocked. |
| `semantic_validator_result` | object | Context privacy and prompt-budget validation result. |
| `not_sent_to_external_model` | boolean | Always `true`. |
| `search_called` | boolean | Always `false`. |
| `saved_by_default` | boolean | Always `false`. |

### Compatibility Endpoints

| Endpoint | Compatibility behavior |
|---|---|
| `GET /api/ai/context-preview` | Returns the existing AI Context Manifest fields plus `full_context_catalogue`, priority counts, exclusion distributions, and local-only execution flags. |
| `POST /api/ai/preview-chat` | Preserves the legacy request/response shape. The free-form question is not used to change the controlled research result. It renders `risk_review`; `structured` uses `standard`, otherwise `brief`. |
| `POST /api/ai/preview-memo` | Preserves legacy memo sections and adds AI-1 research fields. Legacy memo type maps to an answer mode; `detailed` uses `deep`, otherwise `standard`. |
| `POST /api/ai/preview-report` | Preserves the legacy report response and adds AI-1 research fields at `deep` detail. |

The compatibility endpoints remain deterministic local previews. None of them
are an external-model execution endpoint.

## Answer Mode Mapping

| `answer_mode` | Legacy `memo_type` / `report_type` | Chinese purpose |
|---|---|---|
| `daily_brief` | `daily_review_memo` | 每日市场状态、主要压力、约束与观察项。 |
| `risk_review` | `risk_review_memo` | 复核普通回调、宏观压力、信用与系统性风险边界。 |
| `scenario_review` | `scenario_review_memo` | 解释假设冲击、传导通道与不确定条件。 |
| `portfolio_overlay` | `portfolio_overlay_review` | 解释本地清洗后紧凑组合上下文的风险通道。 |
| `evidence_audit` | `evidence_audit_report` | 审计可用事实、模型输出与排除约束。 |
| `research_memo` | `macro_risk_report` | 形成完整中文宏观金融证据复核报告。 |

## Detail Level and Output Budget

AI-1 does not enforce a separate word-count limit. Detail is bounded
deterministically by the maximum number of evidence cards used in each
narrative section:

| `detail_level` | Section card cap | Current budget meaning |
|---|---:|---|
| `brief` | 3 | Compact conclusion and the smallest evidence set. |
| `standard` | 5 | Default review depth and balanced evidence coverage. |
| `deep` | 8 | Broader evidence and constraint coverage without changing the conclusion boundary. |

All three levels share the selected-prompt hard limits:

- maximum selected cards: `96`;
- maximum selected characters: `32,000`;
- maximum locally estimated tokens: `12,000`;
- token estimate: `ceil(character_count / 3)`.

P1 core context is never silently truncated. If P1 alone exceeds a hard limit,
the prompt is marked `not_ready`.

## Seven Research Sections

| Key | Chinese title | Contract |
|---|---|---|
| `current_conclusion` | 当前结论 | States what current evidence supports and does not support. |
| `supporting_evidence` | 支撑证据 | Lists available facts and model-review evidence with context IDs. |
| `counter_evidence` | 反向证据 | Keeps non-escalating evidence separate from missing-data constraints. |
| `data_constraints` | 数据质量与缺失约束 | Aggregates missing, stale, proxy, research-needed, and source-gated exclusions. |
| `macro_explanation` | 宏观金融解释 | Explains credit, funding, rates, inflation, growth, equity, scenario, or historical channels as applicable. |
| `portfolio_channels` | 组合风险通道 | Uses only local sanitized compact context and remains explanatory. |
| `watchlist_and_boundaries` | 观察指标与边界声明 | Lists follow-up evidence and repeats the fixed interpretation boundary. |

Every section carries `source_context` IDs and `claim_tags` for structured
validation.

## Validator Severity

| Severity | Meaning | Display behavior |
|---|---|---|
| `info` | Audit note or missing non-escalating citation. | Displayed for review; output remains visible. |
| `warning` | Evidence quality or contextual limitation. | Displayed for review; output remains visible. |
| `error` | Financial-semantic support or boundary defect. | Requires human review; output remains visible under the current AI-1 policy. |
| `blocker` | Forbidden generated language or privacy marker. | Research body, sections, selected cards, and prompt text are hidden. |

`passed` means no blocker. `max_severity` records the highest finding.

## Seven Financial Semantic Rules

| Rule | Chinese description |
|---|---|
| `systemic_risk_requires_credit_funding_transmission` | 系统性风险复核必须同时引用信用、流动性或融资以及传导证据；单一波动率或权益回撤不能升级为系统性风险结论。 |
| `credit_warning_cannot_rely_only_on_vix_or_etf_proxy` | 信用预警必须引用 HY OAS、IG OAS 或其他信用利差证据；ETF 价格代理不能替代 OAS。 |
| `valuation_pressure_must_acknowledge_missing_or_proxy` | 估值压力必须披露估值、盈利和真实广度数据是否缺失或仅为代理。 |
| `scenario_requires_not_a_forecast_notice` | Scenario Stress Matrix (legacy: D16) 必须被描述为假设传导矩阵，不是预测、事件赔率、收益路径或行动指令。 |
| `historical_validation_requires_not_a_backtest_notice` | Historical Validation Replay (legacy: D19) 必须被描述为事件窗口复盘，不是回测、预测准确率或策略绩效。 |
| `portfolio_requires_local_sanitized_no_allocation` | Portfolio Exposure Overlay (legacy: Stage 8) 只能使用本地清洗后的紧凑上下文，并明确不构成配置或仓位指令。 |
| `financial_stress_score_must_clarify_pressure_temperature` | Financial Stress Composite (legacy: D10) 的评分只能解释为压力温度，不是概率或预测。 |

The structured validator also prevents proxy breadth from confirming true
breadth and prevents portfolio deviation from driving Macro Regime Review
(legacy: D15).

## `prompt_budget` Field Meaning

| Field | Meaning |
|---|---|
| `card_limit` | Maximum selected-card count. |
| `char_limit` | Maximum selected-context character count. |
| `estimated_token_limit` | Maximum conservative local token estimate. |
| `selected_card_count` | Number of cards included after mode filtering. |
| `selected_char_count` | Character count of selected context plus aggregate constraints. |
| `estimated_token_count` | Local estimate; not a provider tokenizer result. |
| `omitted_card_count` | Eligible P2/P3 cards not included in the selected context. |
| `omitted_by_priority` | Omission distribution by P2/P3. |
| `omitted_by_reason` | Omission distribution such as mode filtering or budget exhaustion. |
| `ready` | Whether the local prompt is within hard limits. |
| `status_reason` | Stable machine-readable budget outcome. |

## Selected Prompt Context vs Full Context Catalogue

`full_context_catalogue` is the complete audit surface. It contains all
included evidence cards, included model-output cards, and excluded-constraint
cards. It is never silently truncated.

`selected_prompt_context` is the smaller mode-aware prompt surface:

- P1 core macro state is retained in full;
- P2 and P3 are filtered by answer mode and stable financial reading order;
- P4 excluded constraints enter only as aggregate reason, module, and
  freshness distributions;
- omitted cards remain visible in the full catalogue and in budget
  disclosure counts.

## Privacy Boundary and Persistence

AI-1 consumes the AI Context Manifest only. The manifest exposes sanitized
evidence rows and model outputs that already passed source, freshness, status,
and AI-context gates.

The local preview:

- does not return holdings line items, account values, position weights, or
  transaction history;
- does not return credentials, raw provider payloads, raw prompts, report-file
  contents, or search results;
- does not save the manifest, prompt text, question, answer, or chat history by
  default;
- hides selected context and generated body when a privacy blocker is found;
- always requires human review.

## Relationship to `ai_external_runtime_policy`

AI-1 does not consume the external runtime path. Its effective destination is
`local_preview_only`.

Current local manifest destination flags are:

| Flag | Value |
|---|---:|
| `chat_enabled` | `false` |
| `deepseek_enabled` | `false` |
| `tavily_enabled` | `false` |

`ExternalAIRuntimePolicy` remains fail-closed by default:

- `external_ai_enabled=false`;
- `provider_network_enabled=false`;
- `user_controlled_switch_enabled=false`;
- `single_request_user_approved=false`;
- `context_preview_confirmed=false`;
- `request_built_from_manifest=false`;
- `request_guard_passed=false`;
- search, persistence, background execution, private-account fields, and raw
  prompt/response permissions remain `false`.

AI-1 completion does not change or authorize any of those flags.

## Known Limitations and Handoff

- Output is deterministic template rendering, not model-generated reasoning.
- Detail level changes evidence density, not a separately enforced word count.
- Selected context uses a conservative local token estimate, not a provider
  tokenizer.
- Current AI-1 policy blocks only `blocker`; `error` and `warning` findings
  remain visible for human review.
- Evidence citation coverage is structural context-ID coverage, not a
  natural-language citation-quality score.
- The full context catalogue may be large; prompt selection intentionally
  separates audit completeness from prompt compactness.
- AI-1.5 must add golden fixtures, structure contract coverage, adversarial
  tests, and a reproducible quality audit.
- AI-2 must not start unless the readiness checklist is fully green and the
  user explicitly approves the next phase.
