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
