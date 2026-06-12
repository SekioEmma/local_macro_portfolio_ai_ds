from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OfficialMacroMetric:
    metric_key: str
    display_name: str
    module: str
    source: str
    source_badge: str
    provider: str
    source_series: str | None
    unit: str | None
    expected_frequency: str
    status_when_missing: str
    missing_reason: str
    interpretation_hint: str
    aliases: tuple[str, ...] = ()
    dashboard_enabled: bool = True


OFFICIAL_MACRO_METRICS: dict[str, OfficialMacroMetric] = {
    "dgs2": OfficialMacroMetric(
        metric_key="dgs2",
        display_name="2Y Treasury yield",
        module="rate_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="DGS2",
        unit="percent",
        expected_frequency="daily",
        status_when_missing="missing",
        missing_reason="FRED DGS2 compact observation is missing from local reports.",
        interpretation_hint="FRED DGS2 is a daily Treasury constant maturity yield, not intraday.",
        aliases=("nominal_yield_2y",),
    ),
    "dgs30": OfficialMacroMetric(
        metric_key="dgs30",
        display_name="30Y Treasury yield",
        module="rate_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="DGS30",
        unit="percent",
        expected_frequency="daily",
        status_when_missing="missing",
        missing_reason="FRED DGS30 compact observation is missing from local reports.",
        interpretation_hint="FRED DGS30 is a daily Treasury constant maturity yield, not intraday.",
        aliases=("nominal_yield_30y",),
    ),
    "dfii10": OfficialMacroMetric(
        metric_key="dfii10",
        display_name="10Y real yield",
        module="real_yield_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="DFII10",
        unit="percent",
        expected_frequency="daily",
        status_when_missing="missing",
        missing_reason="FRED DFII10 compact observation is missing from local reports.",
        interpretation_hint="FRED DFII10 is a daily 10-year TIPS real yield observation.",
        aliases=("real_yield_10y",),
    ),
    "t10yie": OfficialMacroMetric(
        metric_key="t10yie",
        display_name="10Y breakeven inflation",
        module="real_yield_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="T10YIE",
        unit="percent",
        expected_frequency="daily",
        status_when_missing="missing",
        missing_reason="FRED T10YIE compact observation is missing from local reports.",
        interpretation_hint="FRED T10YIE is a daily market-implied 10-year breakeven inflation observation.",
        aliases=("breakeven_inflation_10y",),
    ),
    "core_cpi_yoy": OfficialMacroMetric(
        metric_key="core_cpi_yoy",
        display_name="Core CPI YoY",
        module="inflation_energy_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="CPILFESL",
        unit="percent",
        expected_frequency="monthly",
        status_when_missing="missing",
        missing_reason="Core CPI YoY compact observation from FRED CPILFESL is missing from local reports.",
        interpretation_hint="Core CPI YoY should be derived from FRED CPILFESL compact data; it is a monthly inflation-rate measure.",
        aliases=("core_cpi_yoy_pct", "core_cpi"),
    ),
    "core_pce_yoy": OfficialMacroMetric(
        metric_key="core_pce_yoy",
        display_name="Core PCE YoY",
        module="inflation_energy_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="PCEPILFE",
        unit="percent",
        expected_frequency="monthly",
        status_when_missing="missing",
        missing_reason="Core PCE YoY compact observation from FRED PCEPILFE is missing from local reports.",
        interpretation_hint="Core PCE YoY should be derived from FRED PCEPILFE compact data; one observation is not a full inflation trend.",
        aliases=("core_pce_yoy_pct", "core_pce"),
    ),
    "ppiaco_yoy": OfficialMacroMetric(
        metric_key="ppiaco_yoy",
        display_name="PPIACO YoY",
        module="inflation_energy_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="PPIACO",
        unit="percent",
        expected_frequency="monthly",
        status_when_missing="missing",
        missing_reason="FRED PPIACO YoY compact observation is missing from local reports.",
        interpretation_hint="PPIACO YoY is all commodities PPI, not final demand PPI.",
        aliases=("ppi_all_commodities_yoy_pct", "ppiaco_yoy_pct"),
    ),
    "unemployment_rate": OfficialMacroMetric(
        metric_key="unemployment_rate",
        display_name="Unemployment rate",
        module="labor_macro",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="UNRATE",
        unit="percent",
        expected_frequency="monthly",
        status_when_missing="missing",
        missing_reason="FRED UNRATE compact observation is missing from local reports.",
        interpretation_hint="FRED UNRATE is a monthly labor-market observation.",
        aliases=("unrate",),
        dashboard_enabled=False,
    ),
    "initial_jobless_claims": OfficialMacroMetric(
        metric_key="initial_jobless_claims",
        display_name="Initial jobless claims",
        module="labor_macro",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="ICSA",
        unit="claims",
        expected_frequency="weekly",
        status_when_missing="missing",
        missing_reason="FRED ICSA compact observation is missing from local reports.",
        interpretation_hint="FRED ICSA is a weekly initial unemployment claims observation.",
        aliases=("icsa",),
        dashboard_enabled=False,
    ),
    "ppi_final_demand": OfficialMacroMetric(
        metric_key="ppi_final_demand",
        display_name="PPI final demand",
        module="inflation_energy_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="PPIFIS",
        unit="index",
        expected_frequency="monthly",
        status_when_missing="missing",
        missing_reason="FRED PPIFIS PPI final demand compact observation is missing; do not use PPIACO as final demand.",
        interpretation_hint="PPI Final Demand is the official headline final demand PPI index relayed by FRED PPIFIS; it is distinct from PPIACO, monthly/low-frequency, and must not be described as above or below consensus without consensus data.",
        aliases=("ppi_final_demand_index",),
    ),
    "ppi_final_demand_yoy": OfficialMacroMetric(
        metric_key="ppi_final_demand_yoy",
        display_name="PPI final demand YoY",
        module="inflation_energy_pressure",
        source="FRED",
        source_badge="official",
        provider="fred",
        source_series="PPIFIS",
        unit="percent",
        expected_frequency="monthly",
        status_when_missing="insufficient_history",
        missing_reason="PPI final demand YoY requires at least 13 monthly PPIFIS observations; do not use index level as YoY.",
        interpretation_hint="PPI Final Demand YoY is derived from FRED PPIFIS index history; PPIFIS is distinct from PPIACO, monthly/low-frequency, and must not be described as above or below consensus without consensus data.",
        aliases=("ppi_final_demand_yoy_pct",),
    ),
}


def get_official_macro_metric(metric_key: str) -> OfficialMacroMetric | None:
    return OFFICIAL_MACRO_METRICS.get(metric_key)


def dashboard_metric_keys() -> set[str]:
    return {
        metric.metric_key
        for metric in OFFICIAL_MACRO_METRICS.values()
        if metric.dashboard_enabled
    }


def aliases_for(metric_key: str) -> tuple[str, ...]:
    metric = get_official_macro_metric(metric_key)
    return metric.aliases if metric else ()


def metrics_for_module(module: str) -> list[OfficialMacroMetric]:
    return [
        metric
        for metric in OFFICIAL_MACRO_METRICS.values()
        if metric.module == module
    ]


def ppi_final_demand_status() -> str:
    return OFFICIAL_MACRO_METRICS["ppi_final_demand"].status_when_missing
