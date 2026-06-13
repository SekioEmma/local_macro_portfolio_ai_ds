export type ApiResult<T> = {
  data: T | null;
  error: string | null;
};

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
};

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
