const statusClassMap: Record<string, string> = {
  ok: "status-ok",
  watch: "status-watch",
  pressure: "status-pressure",
  stress: "status-stress",
  error: "status-stress",
  degraded: "status-pressure",
  transient_error: "status-pressure",
  missing: "status-missing",
  research_needed: "status-research-needed",
  insufficient_history: "status-insufficient-history",
  stale: "status-stale",
  not_available: "status-missing",
  not_run_yet: "status-muted",
  unknown: "status-unknown"
};

const sourceClassMap: Record<string, string> = {
  official: "source-official",
  official_fallback: "source-official",
  derived: "source-derived",
  "search-derived": "source-derived",
  local: "source-local",
  proxy: "source-proxy",
  unofficial_fallback: "source-proxy",
  missing: "source-muted",
  research_needed: "source-muted"
};

const freshnessClassMap: Record<string, string> = {
  fresh: "freshness-fresh",
  normal_lag: "freshness-normal-lag",
  historical: "freshness-muted",
  stale: "freshness-stale",
  unknown: "freshness-unknown",
  missing: "freshness-missing",
  insufficient_history: "freshness-insufficient-history"
};

export function statusClass(status: string) {
  return statusClassMap[status] || "status-unknown";
}

export function sourceBadgeClass(sourceBadge: string | null | undefined) {
  return sourceClassMap[sourceBadge || "missing"] || "source-muted";
}

export function freshnessClass(freshnessStatus: string | null | undefined) {
  return freshnessClassMap[freshnessStatus || "unknown"] || "freshness-unknown";
}

export function aiContextClass(aiContextAllowed: boolean) {
  return aiContextAllowed ? "ai-allowed" : "ai-blocked";
}
