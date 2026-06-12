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
};

export type DashboardEvidenceFilters = {
  module?: string;
  status?: string;
  source_badge?: string;
  ai_context_allowed?: boolean;
};

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
