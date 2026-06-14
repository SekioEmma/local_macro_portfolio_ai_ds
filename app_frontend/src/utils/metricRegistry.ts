export const metricLabels: Record<string, string> = {
  ppi_final_demand: "PPI 最终需求",
  ppi_final_demand_yoy: "PPI 最终需求同比",
  ppi_final_demand_mom: "PPI 最终需求环比",
  sp500_drawdown_3m: "标普500 3个月回撤",
  sp500_drawdown_6m: "标普500 6个月回撤",
  nasdaq100_drawdown_3m: "纳指100 3个月回撤",
  nasdaq100_drawdown_6m: "纳指100 6个月回撤",
  dgs10_dgs2_curve_slope: "10Y-2Y 曲线斜率",
  dgs30_dgs10_curve_slope: "30Y-10Y 曲线斜率",
  tlt_proxy_30d_return: "TLT 代理30日回报",
  gld_proxy_30d_return: "GLD 代理30日回报",
  shy_proxy_30d_return: "SHY 代理30日回报",
  tlt_vs_shy_30d: "TLT-SHY 30日相对回报"
};

Object.assign(metricLabels, {
  financial_stress_score: "Financial stress score",
  financial_stress_status: "Financial stress status",
  financial_stress_dominant_pressure_source:
    "Financial stress dominant pressure source",
  financial_stress_component_contributions:
    "Financial stress component contributions",
  financial_stress_missing_inputs: "Financial stress missing inputs",
  financial_stress_interpretation_boundary:
    "Financial stress interpretation boundary",
  financial_stress_percentile_context: "Financial stress percentile context",
  financial_stress_funding_liquidity_context:
    "Financial stress funding/liquidity context",
  pullback_classification: "Pullback classification",
  pullback_checklist_items: "Pullback checklist items",
  pullback_missing_critical_inputs: "Pullback missing critical inputs",
  pullback_supporting_evidence: "Pullback supporting evidence",
  pullback_interpretation_boundary: "Pullback interpretation boundary",
  pullback_percentile_context: "Pullback percentile context",
  pullback_liquidity_funding_context: "Pullback liquidity/funding context",
  high_yield_spread_percentile: "High-yield spread percentile",
  high_yield_spread_zscore: "High-yield spread z-score",
  high_yield_spread_robust_zscore: "High-yield spread robust z-score",
  investment_grade_spread_percentile: "Investment-grade spread percentile",
  investment_grade_spread_zscore: "Investment-grade spread z-score",
  investment_grade_spread_robust_zscore:
    "Investment-grade spread robust z-score",
  vix_percentile: "VIX percentile",
  vix_zscore: "VIX z-score",
  vix_robust_zscore: "VIX robust z-score",
  dgs30_percentile: "30Y Treasury yield percentile",
  dgs30_zscore: "30Y Treasury yield z-score",
  dgs30_robust_zscore: "30Y Treasury yield robust z-score",
  dfii10_percentile: "10Y real yield percentile",
  dfii10_zscore: "10Y real yield z-score",
  dfii10_robust_zscore: "10Y real yield robust z-score",
  sp500_drawdown_3m_percentile: "S&P 500 3M drawdown percentile",
  sp500_drawdown_3m_robust_zscore: "S&P 500 3M drawdown robust z-score",
  nasdaq100_drawdown_3m_percentile: "Nasdaq 100 3M drawdown percentile",
  nasdaq100_drawdown_3m_robust_zscore:
    "Nasdaq 100 3M drawdown robust z-score",
  initial_claims_4w_avg_percentile: "Initial claims 4W average percentile",
  initial_claims_4w_avg_robust_zscore:
    "Initial claims 4W average robust z-score",
  continuing_claims_4w_avg_percentile:
    "Continuing claims 4W average percentile",
  continuing_claims_4w_avg_robust_zscore:
    "Continuing claims 4W average robust z-score",
  sofr: "SOFR",
  effr: "Effective federal funds rate",
  iorb: "Interest on reserve balances",
  on_rrp: "ON RRP usage",
  commercial_paper_rate: "Commercial paper rate",
  ofr_fsi: "OFR financial stress index",
  stl_fsi: "St. Louis Fed financial stress index",
  nfci: "Chicago Fed NFCI",
  anfci: "Chicago Fed adjusted NFCI",
  sofr_effr_spread: "SOFR-EFFR spread",
  effr_iorb_spread: "EFFR-IORB spread",
  cp_effr_spread: "CP-EFFR spread",
  cp_sofr_spread: "CP-SOFR spread",
  policy_plumbing_status: "Policy plumbing status",
  short_term_funding_pressure_status: "Short-term funding pressure status",
  official_stress_reference_status: "Official stress reference status",
  liquidity_funding_stress_status: "Liquidity/funding stress status",
  liquidity_funding_interpretation_boundary:
    "Liquidity/funding interpretation boundary",
  growth_macro_status: "Growth macro status",
  growth_macro_supporting_evidence: "Growth macro supporting evidence",
  growth_macro_missing_inputs: "Growth macro missing inputs",
  growth_macro_interpretation_boundary:
    "Growth macro interpretation boundary",
  inflation_macro_status: "Inflation macro status",
  inflation_macro_supporting_evidence:
    "Inflation macro supporting evidence",
  inflation_macro_missing_inputs: "Inflation macro missing inputs",
  inflation_macro_interpretation_boundary:
    "Inflation macro interpretation boundary",
  policy_constraint_status: "Policy constraint status",
  policy_constraint_supporting_evidence:
    "Policy constraint supporting evidence",
  policy_constraint_missing_inputs: "Policy constraint missing inputs",
  policy_constraint_interpretation_boundary:
    "Policy constraint interpretation boundary",
  stagflation_watch_status: "Stagflation watch status",
  stagflation_watch_supporting_evidence:
    "Stagflation watch supporting evidence",
  stagflation_watch_missing_inputs: "Stagflation watch missing inputs",
  stagflation_watch_interpretation_boundary:
    "Stagflation watch interpretation boundary",
  growth_inflation_macro_pack_model_version:
    "Growth/inflation macro pack model version",
  growth_inflation_macro_pack_formula_version:
    "Growth/inflation macro pack formula version",
  growth_inflation_macro_pack_as_of_date:
    "Growth/inflation macro pack as-of date",
  macro_regime_label: "Macro regime label",
  support_band: "Macro regime support band",
  evidence_quality_band: "Macro regime evidence quality band",
  conflict_band: "Macro regime conflict band",
  primary_pressure_ranking: "Primary pressure ranking",
  supporting_evidence: "Macro regime supporting evidence",
  conflicting_evidence: "Macro regime conflicting evidence",
  missing_inputs: "Macro regime missing inputs",
  blocked_inputs: "Macro regime blocked inputs",
  interpretation_boundary: "Macro regime interpretation boundary",
  model_version: "Macro regime model version",
  formula_version: "Macro regime formula version",
  as_of_date: "Macro regime as-of date",
  historical_validation_status: "Historical validation status",
  historical_validation_event_count: "Historical validation event count",
  historical_validation_available_event_count:
    "Historical validation available event count",
  historical_validation_insufficient_history_event_count:
    "Historical validation insufficient history event count",
  historical_validation_ordinary_pullback_over_escalation_count:
    "Historical validation ordinary pullback over-escalation count",
  historical_validation_stress_window_under_escalation_count:
    "Historical validation stress window under-escalation count",
  historical_validation_boundary_violation_count:
    "Historical validation boundary violation count",
  historical_validation_event_window_summary:
    "Historical validation event-window summary",
  historical_validation_privacy_flags: "Historical validation privacy flags",
  historical_validation_validation_boundary: "Historical validation boundary",
  historical_validation_model_version: "Historical validation model version",
  historical_validation_formula_version: "Historical validation formula version",
  historical_validation_as_of_date: "Historical validation as-of date",
  scenario_stress_status: "Scenario stress status",
  scenario_stress_scenario_count: "Scenario stress scenario count",
  scenario_stress_scenarios: "Scenario stress scenarios",
  scenario_stress_primary_scenario: "Scenario stress primary scenario",
  scenario_stress_affected_groups: "Scenario stress affected groups",
  scenario_stress_transmission_channels:
    "Scenario stress transmission channels",
  scenario_stress_severity_band: "Scenario stress severity band",
  scenario_stress_uncertainty_band: "Scenario stress uncertainty band",
  scenario_stress_supporting_evidence:
    "Scenario stress supporting evidence",
  scenario_stress_missing_inputs: "Scenario stress missing inputs",
  scenario_stress_interpretation_boundary:
    "Scenario stress interpretation boundary",
  scenario_stress_model_version: "Scenario stress model version",
  scenario_stress_formula_version: "Scenario stress formula version",
  scenario_stress_as_of_date: "Scenario stress as-of date"
});

