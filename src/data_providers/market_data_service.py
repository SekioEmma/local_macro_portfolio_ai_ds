from __future__ import annotations

import time
from typing import Any

from . import fed_provider, fred_provider  # noqa: F401
from . import market_data_common as _market_data_common

load_manual_market_data = _market_data_common.load_manual_market_data
_asset_type_from_fred_series_config = _market_data_common._asset_type_from_fred_series_config
_asset_type_from_market_symbols = _market_data_common._asset_type_from_market_symbols
_candidate_source_label = _market_data_common._candidate_source_label
_get_manual_market_item = _market_data_common._get_manual_market_item
_optional_mapping = _market_data_common._optional_mapping
_project_root = _market_data_common._project_root
_resolve_path = _market_data_common._resolve_path
_to_float_or_none = _market_data_common._to_float_or_none
_utc_now = _market_data_common._utc_now


MARKET_DATA_KEYS = ("sp500", "nasdaq", "nasdaq100", "gold")
MACRO_DATA_KEYS = ("dgs10", "fedfunds", "cpi", "pce", "nonfarm")
FX_DATA_KEYS = ("usd_cny",)
FINANCIAL_CONDITION_KEYS = (
    "high_yield_spread",
    "investment_grade_spread",
    "vix",
    "real_yield_10y",
    "breakeven_inflation_10y",
    "yield_curve_10y2y",
    "valuation_proxy",
    "fedwatch_probability",
)
TREASURY_NOMINAL_YIELD_KEYS = (
    "nominal_yield_2y",
    "nominal_yield_10y",
    "nominal_yield_30y",
)
INFLATION_INDICATOR_KEYS = (
    "headline_cpi",
    "core_cpi",
    "headline_pce",
    "core_pce",
    "ppi_all_commodities",
    "ppi_final_demand",
)
LABOR_INDICATOR_KEYS = (
    "unemployment_rate",
    "initial_jobless_claims",
)
REQUIRED_CORE_KEYS = (
    "sp500",
    "nasdaq",
    "dgs10",
    "fedfunds",
    "cpi",
    "pce",
    "nonfarm",
    "usd_cny",
)
IMPORTANT_OPTIONAL_KEYS = ("nasdaq100",)
OPTIONAL_MARKET_KEYS = ("gold",)
FRED_PRIMARY_KEYS = REQUIRED_CORE_KEYS


def load_data_source_config(path: str) -> dict:
    config_path = _resolve_path(path)
    raw_text = config_path.read_text(encoding="utf-8")

    try:
        import yaml
    except ImportError:
        config = _load_simple_yaml(raw_text)
    else:
        config = yaml.safe_load(raw_text)

    if not isinstance(config, dict):
        raise ValueError(f"Data source config must contain a mapping: {config_path}")

    return config


def get_core_market_snapshot(config_path: str = "configs/data_sources.yaml") -> dict:
    generated_at = _utc_now()
    _load_project_dotenv()

    config = load_data_source_config(config_path)
    financial_conditions = {
        key: get_financial_condition_item(key, config)
        for key in FINANCIAL_CONDITION_KEYS
    }

    return {
        "market_data": {
            key: get_market_item(key, config)
            for key in MARKET_DATA_KEYS
        },
        "macro_data": {
            key: get_market_item(key, config)
            for key in MACRO_DATA_KEYS
        },
        "fx_data": {
            key: get_market_item(key, config)
            for key in FX_DATA_KEYS
        },
        "financial_conditions": financial_conditions,
        "market_data_package": get_market_data_package(
            config,
            financial_conditions=financial_conditions,
            generated_at=generated_at,
        ),
        "official_sources": fed_provider.get_fed_public_sources(),
        "generated_at": generated_at,
    }


def get_market_data_package(
    config: dict,
    *,
    financial_conditions: dict[str, dict],
    generated_at: str,
) -> dict:
    package_config = _optional_mapping(config, "deepseek_market_data_package")
    treasury_config = _optional_mapping(package_config, "treasury_yields")
    inflation_config = _optional_mapping(package_config, "inflation_indicators")
    oil_config = _optional_mapping(package_config, "oil_and_energy")
    labor_config = _optional_mapping(package_config, "labor_indicators")
    unavailable_config = _optional_mapping(package_config, "unavailable_or_research_needed")

    treasury_yields = {
        key: _fred_package_item(
            key=key,
            item_config=_optional_mapping(treasury_config, key),
            expected_frequency="daily",
            max_stale_days=7,
            timestamp=generated_at,
        )
        for key in TREASURY_NOMINAL_YIELD_KEYS
    }
    treasury_yields.update(_build_treasury_derived_metrics(treasury_yields, generated_at))

    inflation_indicators = {
        key: _package_item_from_config(
            key=key,
            item_config=_optional_mapping(inflation_config, key),
            expected_frequency="monthly",
            max_stale_days=75,
            timestamp=generated_at,
        )
        for key in INFLATION_INDICATOR_KEYS
    }
    inflation_indicators.update(_build_inflation_derived_metrics(inflation_indicators, generated_at))

    oil_and_energy = {
        key: _fred_package_item(
            key=key,
            item_config=_optional_mapping(oil_config, key),
            expected_frequency="daily",
            max_stale_days=7,
            timestamp=generated_at,
        )
        for key in ("wti_oil", "brent_oil")
    }
    oil_and_energy["wti_oil_30d_change"] = _oil_30d_change_item(
        key="wti_oil_30d_change",
        source_item=oil_and_energy["wti_oil"],
        timestamp=generated_at,
    )
    oil_and_energy["brent_oil_30d_change"] = _oil_30d_change_item(
        key="brent_oil_30d_change",
        source_item=oil_and_energy["brent_oil"],
        timestamp=generated_at,
    )

    labor_indicators = {
        key: _fred_package_item(
            key=key,
            item_config=_optional_mapping(labor_config, key),
            expected_frequency="weekly" if key == "initial_jobless_claims" else "monthly",
            max_stale_days=14 if key == "initial_jobless_claims" else 75,
            timestamp=generated_at,
        )
        for key in LABOR_INDICATOR_KEYS
    }

    existing_financial_conditions = {
        key: financial_conditions[key]
        for key in (
            "high_yield_spread",
            "investment_grade_spread",
            "vix",
            "real_yield_10y",
            "breakeven_inflation_10y",
            "yield_curve_10y2y",
        )
        if isinstance(financial_conditions.get(key), dict)
    }
    unavailable = {
        key: _package_unavailable_item(key, item_config, generated_at)
        for key, item_config in unavailable_config.items()
        if isinstance(item_config, dict)
    }

    return {
        "generated_at": generated_at,
        "data_cutoff": _package_data_cutoff(
            treasury_yields,
            inflation_indicators,
            oil_and_energy,
            labor_indicators,
            existing_financial_conditions,
        ),
        "treasury_yields": treasury_yields,
        "inflation_indicators": inflation_indicators,
        "oil_and_energy": oil_and_energy,
        "labor_indicators": labor_indicators,
        "existing_financial_conditions": existing_financial_conditions,
        "unavailable_or_research_needed": unavailable,
        "market_analysis_framework": _market_analysis_framework(),
        "market_regime_classification_rules": _market_regime_classification_rules(),
        "data_limitations": [
            "no intraday Treasury highs",
            "no FedWatch probability",
            "no forward PE / FactSet valuation",
            "no consensus CPI/PPI surprise data",
            "PPI final demand is monthly PPIFIS index data; no consensus surprise data",
            "no market breadth / concentration data",
        ],
        "interpretation_boundaries": [
            "FRED DGS10/DGS30 are daily observations, not intraday highs.",
            "CPI/PCE/PPI are low-frequency inflation data; do not overread one release.",
            "Oil price changes can signal energy pressure but do not alone determine inflation.",
            "Treasury yields near 5% are rate-pressure signals, not standalone trading signals.",
            "Missing FedWatch means no rate-cut probability can be quantified.",
            "Missing valuation data means no exact PE or forward PE claim.",
            "Market judgement must proceed from credit/liquidity -> rates -> inflation/oil -> valuation/earnings -> breadth -> portfolio observation.",
        ],
    }


def get_financial_condition_item(key: str, config: dict) -> dict:
    generated_at = _utc_now()
    financial_config = _financial_condition_config(key, config)
    if not financial_config:
        return _financial_condition_not_configured(
            key=key,
            name=key,
            timestamp=generated_at,
            error=f"financial_conditions.{key} not configured",
        )

    provider = str(financial_config.get("provider") or "").strip().lower()
    name = str(financial_config.get("name") or key)

    if provider == "fred":
        series_id = str(financial_config.get("series_id") or "").strip()
        if not series_id:
            return _financial_condition_not_configured(
                key=key,
                name=name,
                timestamp=generated_at,
                error=f"financial_conditions.{key}.series_id not configured",
                financial_config=financial_config,
            )
        return _fred_financial_condition_item(
            key=key,
            series_id=series_id,
            timestamp=generated_at,
            financial_config=financial_config,
        )

    if provider in {"not_available", "not_configured", "missing_data"}:
        return _financial_condition_not_available(
            key=key,
            name=name,
            timestamp=generated_at,
            financial_config=financial_config,
        )

    return _financial_condition_error(
        key=key,
        name=name,
        timestamp=generated_at,
        error=f"Unsupported financial condition provider: {provider or 'missing'}",
        financial_config=financial_config,
    )


def get_market_item(key: str, config: dict) -> dict:
    generated_at = _utc_now()
    attempts: list[dict] = []
    candidates = _provider_candidates(key, config)
    alpha_vantage_request_sent = False

    if not candidates:
        return _market_error(
            key=key,
            name=key,
            attempts=[
                {
                    "source": "config",
                    "status": "error",
                    "error": f"No provider candidates configured for {key}",
                    "timestamp": generated_at,
                }
            ],
            timestamp=generated_at,
        )

    result_name = _first_candidate_name(candidates, key)
    asset_type = _first_candidate_asset_type(candidates)
    primary_source = _candidate_source_label(candidates[0]) if candidates else None

    for candidate in candidates:
        call_candidate = candidate
        if candidate.get("provider") == "alpha_vantage" and alpha_vantage_request_sent:
            delay_seconds = _alpha_vantage_request_delay_seconds(config)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
                call_candidate = {**candidate, "delay_applied_seconds": delay_seconds}

        result = _call_provider(call_candidate)
        if candidate.get("provider") == "alpha_vantage" and result.get("request_sent"):
            alpha_vantage_request_sent = True
        attempts.append(_attempt_summary(call_candidate, result))

        value = _to_float_or_none(result.get("value"))
        if result.get("status") == "ok" and value is not None:
            item = {
                "key": key,
                "name": candidate.get("name") or result_name,
                "asset_type": candidate.get("asset_type") or asset_type,
                "value": value,
                "source": result.get("source") or candidate["provider"],
                "timestamp": result.get("timestamp") or generated_at,
                "status": "ok",
                "error": None,
                "attempted_sources": attempts,
                "primary_source": primary_source,
                "fallback_used": bool(candidate.get("fallback_used")),
            }
            if candidate.get("fallback_reason"):
                item["fallback_reason"] = candidate["fallback_reason"]
            if result.get("definition_note") or candidate.get("definition_note"):
                item["definition_note"] = result.get("definition_note") or candidate.get("definition_note")
            if result.get("series_id") or candidate.get("series_id"):
                item["series_id"] = result.get("series_id") or candidate.get("series_id")
            if result.get("fallback_series") or candidate.get("fallback_series"):
                item["fallback_series"] = result.get("fallback_series") or candidate.get("fallback_series")
            for metadata_key in (
                "bea_dataset",
                "table",
                "line",
                "frequency",
                "unit",
                "source_series",
                "rate_type",
                "volume_in_billions",
            ):
                if result.get(metadata_key) is not None:
                    item[metadata_key] = result[metadata_key]
            if result.get("symbol") or candidate.get("symbol"):
                item["symbol"] = result.get("symbol") or candidate.get("symbol")
            if result.get("observation_date"):
                item["observation_date"] = result["observation_date"]
            if result.get("currency"):
                item["currency"] = result["currency"]
            if result.get("function") or candidate.get("function"):
                item["function"] = result.get("function") or candidate.get("function")
            if result.get("source_tier") or candidate.get("source_tier"):
                item["source_tier"] = result.get("source_tier") or candidate.get("source_tier")
            if result.get("updated_at"):
                item["updated_at"] = result["updated_at"]
            if result.get("path"):
                item["path"] = result["path"]
            if candidate.get("notes"):
                item["notes"] = candidate["notes"]
            if result.get("notes"):
                item["notes"] = result["notes"]
            return item

    return _market_error(
        key=key,
        name=result_name,
        attempts=attempts,
        timestamp=generated_at,
        asset_type=asset_type,
    )


def _market_analysis_framework() -> dict[str, dict[str, Any]]:
    return {
        "step_1_credit_and_financial_stress": {
            "purpose": "First judge whether there is evidence of systemic crisis.",
            "inputs": ["high_yield_spread", "investment_grade_spread if available", "financial_stress_index if available", "vix"],
            "rule": "When credit spreads and financial stress are normal, do not classify an equity pullback as systemic crisis only because prices fell.",
        },
        "step_2_nominal_and_real_rates": {
            "purpose": "Judge whether valuation pressure comes from nominal yields, real yields, or curve structure.",
            "inputs": ["DGS2", "DGS10", "DGS30", "DFII10", "T10Y2Y", "DGS10/DGS30 recent highs"],
            "rule": "10Y/30Y near or above 5% is a rate-pressure signal, not a standalone trading signal.",
        },
        "step_3_inflation_and_oil": {
            "purpose": "Judge whether inflation and energy pressure constrain easing.",
            "inputs": ["CPI", "core CPI", "PCE", "core PCE", "PPIACO", "WTI", "Brent", "T10YIE"],
            "rule": "Rising oil can add inflation pressure, but it must not be mechanically equated with runaway inflation.",
        },
        "step_4_valuation_and_earnings_boundary": {
            "purpose": "Judge whether valuation and earnings can be discussed as facts.",
            "inputs": ["valuation_proxy", "forward_pe", "cape", "earnings_revision"],
            "rule": "If valuation and earnings data are not_available, say the package cannot confirm valuation level; do not invent PE or forward PE.",
        },
        "step_5_market_structure_boundary": {
            "purpose": "Judge whether market gains are overly concentrated.",
            "inputs": ["market_breadth", "equal_weight_vs_cap_weight", "mega_cap_concentration"],
            "rule": "If breadth and concentration data are missing, do not assert that AI/mega-cap concentration has worsened; mark it as an observation gap.",
        },
        "step_6_portfolio_observation": {
            "purpose": "Only then translate the macro state into long-term portfolio observation.",
            "allowed_language": ["relative overweight/underweight versus target", "risk exposure rising/falling", "future DCA evaluation", "threshold review", "year-end review", "rebalancing evaluation"],
            "forbidden_language": ["should buy", "should sell", "liquidate", "wait for a dip", "adjust immediately", "specific buy/sell amount"],
        },
    }


def _market_regime_classification_rules() -> dict[str, dict[str, Any]]:
    return {
        "normal_pullback": {
            "evidence": ["equity drawdown or volatility", "credit spreads still normal", "VIX not showing panic", "no systemic deterioration in earnings, jobs, or funding"],
            "boundary": "Do not automatically upgrade normal pullback to crisis.",
        },
        "sideways_valuation_digest": {
            "evidence": ["rates elevated", "earnings not broken", "valuation data missing or high pending confirmation", "indices move sideways or churn"],
            "boundary": "Sideways digestion may be more realistic than a fast V-shaped repair, but do not forecast timing.",
        },
        "rates_inflation_shock": {
            "evidence": ["DGS10/DGS30 rising", "real yield rising", "CPI/PPI/PCE or oil pressure", "equities, bonds, and gold can all face pressure"],
            "boundary": "Inflation shock differs from ordinary safe-haven risk.",
        },
        "trend_reversal": {
            "evidence": ["earnings revisions down", "market breadth deterioration", "rates/dollar/liquidity persistently pressuring assets"],
            "boundary": "If earnings and breadth data are missing, do not confirm trend reversal.",
        },
        "systemic_crisis": {
            "evidence": ["credit spreads widen materially", "financial stress rises", "funding, banks, jobs, and earnings show multi-signal deterioration"],
            "boundary": "Without multi-signal confirmation, do not confirm systemic crisis.",
        },
        "ai_bubble_risk": {
            "evidence": ["real technology trend", "valuation overextension", "earnings delivery insufficient", "capex return uncertain", "concentration rising", "high real yields pressuring duration"],
            "boundary": "If valuation, earnings, and concentration data are missing, discuss mechanism only; do not confirm bubble magnitude.",
        },
    }


def _attempt_summary(candidate: dict, result: dict) -> dict:
    summary = {
        "source": result.get("source") or candidate.get("source") or candidate["provider"],
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp") or _utc_now(),
    }

    if candidate.get("series_id") or result.get("series_id"):
        summary["series_id"] = result.get("series_id") or candidate.get("series_id")
    if candidate.get("primary_source") or result.get("primary_source"):
        summary["primary_source"] = result.get("primary_source") or candidate.get("primary_source")
    if candidate.get("fallback_used") is not None:
        summary["fallback_used"] = bool(candidate.get("fallback_used"))
    if candidate.get("fallback_reason") or result.get("fallback_reason"):
        summary["fallback_reason"] = result.get("fallback_reason") or candidate.get("fallback_reason")
    if result.get("definition_note") or candidate.get("definition_note"):
        summary["definition_note"] = result.get("definition_note") or candidate.get("definition_note")
    if result.get("fallback_series") or candidate.get("fallback_series"):
        summary["fallback_series"] = result.get("fallback_series") or candidate.get("fallback_series")
    if candidate.get("symbol") or result.get("symbol"):
        summary["symbol"] = result.get("symbol") or candidate.get("symbol")
    if result.get("observation_date"):
        summary["observation_date"] = result["observation_date"]
    if result.get("currency"):
        summary["currency"] = result["currency"]
    if candidate.get("function") or result.get("function"):
        summary["function"] = result.get("function") or candidate.get("function")
    if result.get("source_tier") or candidate.get("source_tier"):
        summary["source_tier"] = result.get("source_tier") or candidate.get("source_tier")
    for metadata_key in ("frequency", "unit", "source_series"):
        if result.get(metadata_key) or candidate.get(metadata_key):
            summary[metadata_key] = result.get(metadata_key) or candidate.get(metadata_key)
    if candidate.get("path") or result.get("path"):
        summary["path"] = result.get("path") or candidate.get("path")
    if result.get("updated_at"):
        summary["updated_at"] = result["updated_at"]
    if candidate.get("notes"):
        summary["notes"] = candidate["notes"]
    if result.get("notes"):
        summary["notes"] = result["notes"]
    if result.get("request_sent") is not None:
        summary["request_sent"] = bool(result.get("request_sent"))
    if candidate.get("delay_applied_seconds") is not None:
        summary["delay_applied_seconds"] = candidate["delay_applied_seconds"]

    return summary


def _market_error(
    key: str,
    name: str,
    attempts: list[dict],
    timestamp: str,
    asset_type: str | None = None,
) -> dict:
    errors = [
        f"{_attempt_label(attempt)}: {attempt.get('error')}"
        for attempt in attempts
        if attempt.get("error")
    ]
    error = "; ".join(errors) or "All configured market data sources failed"

    return {
        "key": key,
        "name": name,
        "asset_type": asset_type,
        "value": None,
        "source": "market_data_service",
        "timestamp": timestamp,
        "status": "error",
        "error": error,
        "attempted_sources": attempts,
    }


def _attempt_label(attempt: dict) -> str:
    label = str(attempt.get("source") or "unknown")
    if attempt.get("function"):
        label = f"{label} {attempt['function']}"
    if attempt.get("series_id"):
        return f"{label} {attempt['series_id']}"
    if attempt.get("symbol"):
        return f"{label} {attempt['symbol']}"
    return label


def _alpha_vantage_request_delay_seconds(config: dict) -> float:
    alpha_vantage_config = _optional_mapping(config, "alpha_vantage")
    raw_delay = alpha_vantage_config.get("request_delay_seconds", 0)
    try:
        delay_seconds = float(raw_delay)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, delay_seconds)


def _first_candidate_name(candidates: list[dict], fallback: str) -> str:
    for candidate in candidates:
        if candidate.get("name"):
            return str(candidate["name"])
    return fallback


def _first_candidate_asset_type(candidates: list[dict]) -> str | None:
    for candidate in candidates:
        if candidate.get("asset_type"):
            return str(candidate["asset_type"])
    return None


def _load_project_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(_project_root() / ".env")
    load_dotenv()


def _load_simple_yaml(raw_text: str) -> dict:
    lines = raw_text.splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"Unsupported YAML list item on line {index + 1}.")
            parent.append(_parse_simple_yaml_scalar(content[2:].strip()))
            continue

        if ":" not in content:
            raise ValueError(f"Unsupported YAML syntax on line {index + 1}.")

        key, value = content.split(":", 1)
        key = _parse_simple_yaml_key(key.strip())
        value = value.strip()

        if value:
            parent[key] = _parse_simple_yaml_scalar(value)
            continue

        child = [] if _next_content_is_list(lines, index, indent) else {}
        parent[key] = child
        stack.append((indent, child))

    return root


def _next_content_is_list(lines: list[str], current_index: int, current_indent: int) -> bool:
    for line in lines[current_index + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        return indent > current_indent and line.strip().startswith("- ")
    return False


def _parse_simple_yaml_key(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_simple_yaml_scalar(value: str) -> Any:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    lower_value = value.lower()
    if lower_value == "true":
        return True
    if lower_value == "false":
        return False
    if lower_value in {"null", "none", "~"}:
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


from .market_data_packaging import (  # noqa: E402, F401
    _bea_config,
    _bls_config,
    _derived_package_error,
    _financial_condition_base,
    _financial_condition_config,
    _financial_condition_error,
    _financial_condition_not_available,
    _financial_condition_not_configured,
    _fred_financial_condition_item,
    _fred_package_item,
    _official_fallback_for_fred_series,
    _package_attempt,
    _package_data_cutoff,
    _package_freshness,
    _package_item,
    _package_item_from_config,
    _package_unavailable_item,
    _source_error_derived_item,
)


from .market_derived_metrics import (  # noqa: E402, F401
    _add_months,
    _above_5pct_days_item,
    _above_5pct_item,
    _breakout_confirmed_item,
    _build_inflation_derived_metrics,
    _build_treasury_derived_metrics,
    _distance_to_5pct_item,
    _fred_history,
    _inflation_change_item,
    _latest_available_observations,
    _monthly_comparison_observation,
    _nearest_observation,
    _oil_30d_change_item,
    _parse_date,
    _recent_high_item,
    _threshold_average_item,
)


from .market_provider_candidates import (  # noqa: E402, F401
    _alpha_vantage_candidate,
    _bea_candidate,
    _bls_candidate,
    _call_provider,
    _fedfunds_candidate,
    _fred_candidate,
    _fred_candidates_with_fallbacks,
    _manual_candidate,
    _provider_candidates,
    _treasury_yield_candidate,
    _yfinance_candidate,
)

