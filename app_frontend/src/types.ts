export type ApiResult<T> = {
  data: T | null;
  error: string | null;
};

// App shell and diagnostics API responses.
export type StatusResponse = {
  app_name: string;
  mode: string;
  storage_mode: string;
  api_keys_configured: Record<string, boolean>;
  privacy_boundaries: string[];
  project_root_exists: boolean;
};

export type ProviderHealthCheck = {
  key: string;
  provider: string;
  status: string;
  source: string | null;
  observation_date: string | null;
  value_present: boolean | null;
  error_type: string | null;
  error_summary: string | null;
};

export type ProviderHealthResponse = {
  generated_at: string | null;
  overall_status: string;
  summary: Record<string, number>;
  checks: ProviderHealthCheck[];
  next_action: string | null;
  error_summary: string | null;
};

// Dashboard summary and evidence API responses.
export type DashboardModule = {
  key: string;
  status: string;
  label: string | null;
  summary: string | null;
  source_badge: string | null;
  updated_at: string | null;
  next_action: string | null;
  error_summary: string | null;
  key_metrics: DashboardMetric[];
};

export type DashboardMetric = {
  metric_key: string;
  display_name: string;
  value: number | string | boolean | null;
  value_text: string;
  unit: string | null;
  status: string;
  source: string | null;
  source_badge: string;
  source_series: string | null;
  observation_date: string | null;
  generated_at: string | null;
  freshness_status: string;
  missing_reason: string | null;
  interpretation_hint: string | null;
  ai_context_allowed: boolean;
  input_evidence?: Array<Record<string, unknown>> | null;
  component_contributions?: Record<string, unknown> | null;
  missing_inputs?: string[] | null;
  interpretation_boundary?: string | null;
  lookback_window?: string | null;
  lookback_start?: string | null;
  lookback_end?: string | null;
  observation_count?: number | null;
  minimum_observation_count?: number | null;
  history_quality_status?: string | null;
  percentile?: number | null;
  percentile_band?: string | null;
  zscore?: number | null;
  zscore_band?: string | null;
  robust_zscore?: number | null;
  robust_zscore_band?: string | null;
  percentile_direction?: string | null;
  frequency_class?: string | null;
  transform_class?: string | null;
  ai_context_tier?: string | null;
  trigger_eligibility?: string | null;
};

export type DashboardSummaryResponse = {
  generated_at: string | null;
  overall_status: string;
  overall_risk_level: string | null;
  modules: Record<string, DashboardModule>;
  provider_health: {
    generated_at?: string | null;
    overall_status?: string | null;
    summary?: Record<string, number>;
    next_action?: string | null;
    error_summary?: string | null;
  };
  missing_data: Array<Record<string, unknown>>;
  data_freshness: Record<string, unknown>;
  next_actions: string[];
};

export type DashboardEvidenceRow = {
  row_id: string;
  module: string;
  metric_key: string;
  display_name: string;
  value: number | string | boolean | null;
  value_text: string;
  unit: string | null;
  status: string;
  source: string | null;
  source_badge: string;
  source_series: string | null;
  observation_date: string | null;
  generated_at: string | null;
  freshness_status: string;
  missing_reason: string | null;
  interpretation_hint: string | null;
  blocked_reason: string | null;
  ai_context_allowed: boolean;
  input_evidence?: Array<Record<string, unknown>> | null;
  component_contributions?: Record<string, unknown> | null;
  missing_inputs?: string[] | null;
  interpretation_boundary?: string | null;
  lookback_window?: string | null;
  lookback_start?: string | null;
  lookback_end?: string | null;
  observation_count?: number | null;
  minimum_observation_count?: number | null;
  history_quality_status?: string | null;
  percentile?: number | null;
  percentile_band?: string | null;
  zscore?: number | null;
  zscore_band?: string | null;
  robust_zscore?: number | null;
  robust_zscore_band?: string | null;
  percentile_direction?: string | null;
  frequency_class?: string | null;
  transform_class?: string | null;
  ai_context_tier?: string | null;
  trigger_eligibility?: string | null;
};

export type DashboardEvidenceFilters = {
  module?: string;
  status?: string;
  source_badge?: string;
  ai_context_allowed?: boolean;
};

export type DashboardEvidenceModuleKey =
  | "financial_stress_composite"
  | "historical_risk_percentile"
  | "liquidity_funding_stress"
  | "pullback_systemic_risk_checklist"
  | string;

export type DashboardEvidenceTableResponse = {
  generated_at: string | null;
  overall_status: string;
  row_count: number;
  modules: string[];
  rows: DashboardEvidenceRow[];
  filters: {
    available?: {
      modules?: string[];
      statuses?: string[];
      source_badges?: string[];
      ai_context_allowed?: boolean[];
    };
    applied?: Record<string, string | boolean | null>;
  };
  next_actions: string[];
};

export type AIContextManifestResponse = {
  generated_at: string | null;
  included_facts: Array<Record<string, unknown>>;
  excluded_facts: Array<Record<string, unknown>>;
  included_model_outputs: Array<Record<string, unknown>>;
  excluded_model_outputs: Array<Record<string, unknown>>;
  portfolio_context_policy: Record<string, unknown>;
  privacy_policy: Record<string, unknown>;
  search_policy: Record<string, unknown>;
  model_destination: Record<string, unknown>;
  persistence_policy: Record<string, unknown>;
  risk_boundaries: string[];
  source_summary: Record<string, unknown>;
  mode?: "local_preview";
  search_enabled?: boolean;
  external_model_called?: boolean;
  search_called?: boolean;
  saved_by_default?: boolean;
  included_fact_count?: number;
  excluded_fact_count?: number;
  included_model_output_count?: number;
  excluded_model_output_count?: number;
  context_stats?: Record<string, unknown>;
  last_generated_at?: string | null;
  full_context_catalogue?: AIFullContextCatalogue;
  priority_counts?: Record<string, number>;
  excluded_reason_distribution?: Record<string, number>;
};

export type AIAnswerMode =
  | "daily_brief"
  | "risk_review"
  | "scenario_review"
  | "portfolio_overlay"
  | "evidence_audit"
  | "research_memo";

export type AIDetailLevel = "brief" | "standard" | "deep";
export type AIValidationSeverity = "info" | "warning" | "error" | "blocker";

export type AIContextCard = {
  card_type: string;
  module: string;
  module_display_zh: string;
  metric_key: string;
  display_name: string;
  priority: number;
  priority_label_zh: string;
  value_text?: string | null;
  status?: string | null;
  status_display_zh?: string | null;
  source_badge?: string | null;
  source_badge_display_zh?: string | null;
  freshness_status?: string | null;
  freshness_display_zh?: string | null;
  observation_date?: string | null;
  interpretation_hint?: string | null;
  interpretation_boundary?: string | null;
  trigger_eligibility?: string | null;
  trigger_eligibility_display_zh?: string | null;
  support_band?: string | null;
  severity_band?: string | null;
  uncertainty_band?: string | null;
  evidence_quality_band?: string | null;
  conflict_band?: string | null;
  missing_input_count?: number | null;
  excluded_reason?: string | null;
  excluded_reason_display_zh?: string | null;
  effect_zh?: string | null;
  boundary_notice_zh: string;
};

export type AIFullContextCatalogue = {
  evidence_cards: AIContextCard[];
  model_output_cards: AIContextCard[];
  excluded_constraint_cards: AIContextCard[];
  total_card_count: number;
  priority_counts: Record<string, number>;
  source_badge_distribution: Record<string, number>;
  excluded_reason_distribution: Record<string, number>;
};

export type AIConstraintSummary = {
  total_count: number;
  excluded_reason_distribution: Record<string, number>;
  module_distribution: Record<string, number>;
  freshness_distribution: Record<string, number>;
  summary_zh: string;
};

export type AIPromptBudgetSummary = {
  card_limit: number;
  char_limit: number;
  estimated_token_limit: number;
  selected_card_count: number;
  selected_char_count: number;
  estimated_token_count: number;
  omitted_card_count: number;
  omitted_by_priority: Record<string, number>;
  omitted_by_reason: Record<string, number>;
  ready: boolean;
  status_reason: string;
};

export type AISelectedPromptContext = {
  selected_cards: AIContextCard[];
  constraint_summary: AIConstraintSummary;
  selected_context_text: string;
  selection_notes: string[];
};

export type AISemanticFinding = {
  code: string;
  category: string;
  severity: AIValidationSeverity;
  message_zh: string;
  matched_claims: string[];
  cited_context_ids: string[];
  required_context: string[];
};

export type AIResearchValidationResult = {
  passed: boolean;
  blocked: boolean;
  max_severity: AIValidationSeverity | null;
  findings: AISemanticFinding[];
  domain_checks: Record<string, string>;
};

export type AIResearchSection = {
  key:
    | "current_conclusion"
    | "supporting_evidence"
    | "counter_evidence"
    | "data_constraints"
    | "macro_explanation"
    | "portfolio_channels"
    | "watchlist_and_boundaries";
  title: string;
  content: string;
  source_context: string[];
  claim_tags: string[];
};

export type AIResearchPreviewResponse = {
  mode: "local_controlled_research_preview";
  answer_mode: AIAnswerMode;
  legacy_memo_type: string;
  detail_level: AIDetailLevel;
  title: string;
  answer_preview: string;
  research_sections: AIResearchSection[];
  selected_prompt_context: AISelectedPromptContext;
  prompt_budget: AIPromptBudgetSummary;
  context_used_summary: {
    included_fact_count: number;
    excluded_fact_count: number;
    included_model_output_count: number;
    excluded_model_output_count: number;
  };
  privacy_summary: Record<string, boolean>;
  validator_result: {
    passed: boolean;
    blocked_terms: string[];
    privacy_findings: string[];
  };
  semantic_validator_result: AIResearchValidationResult;
  not_sent_to_external_model: boolean;
  human_review_required: boolean;
  interpretation_boundary: string;
};

export type AIPromptPreviewResponse = {
  mode: "local_prompt_preview";
  status: "ready" | "not_ready";
  answer_mode: AIAnswerMode;
  legacy_memo_type: string;
  detail_level: AIDetailLevel;
  system_boundary: string;
  task_instruction: string;
  selected_prompt_context: AISelectedPromptContext;
  output_contract: string[];
  preflight_checklist: string[];
  prompt_budget: AIPromptBudgetSummary;
  prompt_text: string;
  semantic_validator_result: AIResearchValidationResult;
  not_sent_to_external_model: boolean;
  search_called: boolean;
  saved_by_default: boolean;
};

export type AIDeepSeekClaimMetadata = {
  claim_type_counts: Record<string, number>;
  threshold_source_counts: Record<string, number>;
  total_claims: number;
};

export type AIDeepSeekResearchResponse = {
  mode: "deepseek_single_turn";
  response_kind: "research" | "guidance";
  answer_mode: AIAnswerMode;
  detail_level: AIDetailLevel;
  user_question: string;
  deepseek_raw_output: string;
  deepseek_memo_output: string;
  claim_metadata: AIDeepSeekClaimMetadata;
  finish_reason: string;
  selected_prompt_context: AISelectedPromptContext;
  prompt_budget: AIPromptBudgetSummary;
  prompt_text: string;
  context_used_summary: {
    included_fact_count: number;
    excluded_fact_count: number;
    included_model_output_count: number;
    excluded_model_output_count: number;
  };
  privacy_summary: Record<string, boolean>;
  validator_result: {
    passed: boolean;
    blocked_terms: string[];
    privacy_findings: string[];
  };
  semantic_validator_result: AIResearchValidationResult;
  input_validation_passed: boolean;
  input_validation_findings: string[];
  output_blocked: boolean;
  human_review_required: boolean;
  interpretation_boundary: string;
  elapsed_seconds: number | null;
  model_provider: string;
  not_saved_by_default: boolean;
};

export type AgentSourceVisibilityMode = "public" | "debug";

export type AgentRunRequest = {
  user_question: string;
  session_id?: string | null;
  include_holdings?: boolean;
  holdings_consent_token?: string | null;
  confirm_external_search?: boolean;
  source_visibility_mode?: AgentSourceVisibilityMode;
};

export type AgentFinalStatus =
  | "ok"
  | "incomplete"
  | "validation_failed"
  | "cancelled"
  | "unavailable";

export type AgentSseEventType =
  | "run_started"
  | "information_plan"
  | "phase_changed"
  | "provider_call_started"
  | "provider_call_finished"
  | "tool_call_started"
  | "tool_result"
  | "evidence_registered"
  | "warning"
  | "brief_validated"
  | "brief_section"
  | "complete"
  | "cancelled"
  | "error";

export type AgentSseEvent = {
  event_id: string;
  session_id: string;
  sequence: number;
  timestamp: string;
  type: AgentSseEventType | string;
  payload: Record<string, unknown>;
};

export type AgentBriefSection = {
  section: string;
  content: unknown;
  sequence: number;
};

export type AgentStreamResult = {
  session_id: string | null;
  final_status: AgentFinalStatus | string | null;
  trace_session_id: string | null;
  steps: number | null;
};

export type AgentCancelResponse = {
  session_id: string;
  cancelled: boolean;
  already_cancelled: boolean;
};

// Local app-state API responses.
export type StorageStatusResponse = {
  storage_mode: string;
  database_exists: boolean;
  schema_version: number | null;
  initialized: boolean;
  error_summary: string | null;
};

export type AppSettingsResponse = {
  settings: AppSettings;
  updated_at: string | null;
};

export type AppSettings = {
  ui_language?: string;
  default_context_mode?: string;
  search_enabled_by_default?: boolean;
  save_chat_by_default?: boolean;
  show_cost_detail?: string;
};

export type RefreshRun = {
  id: number;
  kind: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  summary: Record<string, unknown>;
  error_summary: string | null;
  created_at: string;
};

export type FavoriteAnswer = {
  id: number;
  title: string | null;
  question: string;
  answer: string;
  model: string | null;
  context_snapshot: Record<string, unknown>;
  created_at: string;
};
