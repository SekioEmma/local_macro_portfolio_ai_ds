from __future__ import annotations

from . import (
    alpha_vantage_provider,
    bea_provider,
    bls_provider,
    fedfunds_provider,
    fred_provider,
    treasury_provider,
    yfinance_provider,
)
from .market_data_common import (
    _asset_type_from_fred_series_config,
    _asset_type_from_market_symbols,
    _candidate_source_label,
    _get_manual_market_item,
    _optional_mapping,
    _utc_now,
)
from .market_data_packaging import _bea_config, _bls_config


def _provider_candidates(key: str, config: dict) -> list[dict]:
    if key == "fedfunds":
        return [
            _fred_candidate(key, config),
            _fedfunds_candidate(),
        ]

    if key == "pce":
        return [
            _fred_candidate(key, config),
            _bea_candidate("headline_pce", config),
        ]

    if key in {"cpi", "nonfarm"}:
        return [
            _fred_candidate(key, config),
            _bls_candidate(key, config),
        ]

    if key in {"sp500", "nasdaq"}:
        return [
            _fred_candidate(key, config),
            _yfinance_candidate(
                key,
                config,
                notes="Yahoo Finance market quote fallback; not official macro/statistical source.",
                fallback_used=True,
            ),
        ]

    if key == "dgs10":
        return [
            _fred_candidate(key, config),
            _treasury_yield_candidate("DGS10", "10y"),
        ]

    if key == "usd_cny":
        return [
            _fred_candidate(
                key,
                config,
                notes="FRED DEXCHUS reports Chinese yuan per 1 U.S. dollar (CNY per USD).",
            ),
            _yfinance_candidate(
                key,
                config,
                notes="Yahoo CNY=X is treated as USD/CNY, CNY per 1 USD.",
                fallback_used=True,
            ),
        ]

    if key == "nasdaq100":
        return [
            _fred_candidate(key, config),
            _yfinance_candidate(key, config, fallback_used=True),
        ]

    if key == "gold":
        return [
            _alpha_vantage_candidate(key, config, mode="spot"),
            _alpha_vantage_candidate(key, config, mode="history"),
            _manual_candidate(key, config),
            _yfinance_candidate(key, config),
        ]

    return []


def _fred_candidate(key: str, config: dict, notes: str | None = None) -> dict:
    fred_series = _optional_mapping(config, "fred_series")
    series_config = fred_series.get(key)

    if not isinstance(series_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"fred_series.{key} not configured",
        }

    series_id = series_config.get("series_id")
    if not series_id:
        return {
            "provider": "config",
            "source": "config",
            "name": series_config.get("name") or key,
            "asset_type": series_config.get("asset_type"),
            "error": f"fred_series.{key}.series_id not configured",
        }

    candidate = {
        "provider": "fred",
        "series_id": str(series_id),
        "name": series_config.get("name") or key,
        "asset_type": series_config.get("asset_type"),
        "source_tier": "official_api",
    }
    if notes:
        candidate["notes"] = notes
    return candidate


def _fred_candidates_with_fallbacks(
    key: str,
    config: dict,
    notes: str | None = None,
) -> list[dict]:
    primary = _fred_candidate(key, config, notes=notes)
    candidates = [primary]
    if primary.get("provider") != "fred":
        return candidates

    fred_series = _optional_mapping(config, "fred_series")
    series_config = fred_series.get(key, {})
    if not isinstance(series_config, dict):
        return candidates

    fallback_series_ids = series_config.get("fallback_series_ids", [])
    if isinstance(fallback_series_ids, str):
        fallback_series_ids = [fallback_series_ids]

    for fallback_series_id in fallback_series_ids:
        fallback_series_id = str(fallback_series_id).strip()
        if not fallback_series_id:
            continue
        candidates.append(
            {
                "provider": "fred",
                "series_id": fallback_series_id,
                "name": series_config.get("name") or key,
                "asset_type": series_config.get("asset_type"),
            }
        )

    return candidates


def _manual_candidate(key: str, config: dict) -> dict:
    manual_config = _optional_mapping(config, "manual_market_data")
    manual_path = manual_config.get("file") or "data/manual/market_data_manual.csv"
    return {
        "provider": "manual",
        "key": key,
        "path": str(manual_path),
        "name": f"{key} manual market data",
        "asset_type": _asset_type_from_market_symbols(key, config),
    }


def _alpha_vantage_candidate(key: str, config: dict, mode: str) -> dict:
    alpha_vantage_config = _optional_mapping(config, "alpha_vantage")
    gold_config = alpha_vantage_config.get("gold", {})
    if not alpha_vantage_config.get("enabled", False):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": "commodity",
            "error": "alpha_vantage.enabled is false",
        }
    if not isinstance(gold_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": "commodity",
            "error": "alpha_vantage.gold not configured",
        }

    if mode == "spot":
        function_name = gold_config.get("spot_function") or "GOLD_SILVER_SPOT"
        name = "Gold spot price"
    else:
        function_name = gold_config.get("history_function") or "GOLD_SILVER_HISTORY"
        name = "Gold daily history latest price"

    return {
        "provider": "alpha_vantage",
        "mode": mode,
        "function": str(function_name),
        "symbol": str(gold_config.get("symbol") or "GOLD"),
        "interval": str(gold_config.get("interval") or "daily"),
        "name": name,
        "asset_type": "commodity",
        "source_tier": "third_party_api",
    }


def _yfinance_candidate(
    key: str,
    config: dict,
    notes: str | None = None,
    fallback_used: bool = True,
) -> dict:
    market_symbols = _optional_mapping(config, "market_symbols")
    symbol_config = market_symbols.get(key)

    if not isinstance(symbol_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"market_symbols.{key} not configured",
        }

    symbol = symbol_config.get("symbol")
    if not symbol:
        return {
            "provider": "config",
            "source": "config",
            "name": symbol_config.get("name") or key,
            "asset_type": symbol_config.get("asset_type"),
            "error": f"market_symbols.{key}.symbol not configured",
        }

    candidate = {
        "provider": "yfinance",
        "symbol": str(symbol),
        "name": symbol_config.get("name") or key,
        "asset_type": symbol_config.get("asset_type"),
        "source_tier": "unofficial_fallback",
        "definition_note": "Yahoo Finance market quote fallback; not official macro/statistical source.",
        "fallback_used": fallback_used,
        "fallback_reason": "primary_source_unavailable",
    }
    if notes:
        candidate["notes"] = notes
    return candidate


def _bls_candidate(key: str, config: dict) -> dict:
    item_config = _bls_config(config, key)
    series_id = str(item_config.get("series_id") or "").strip()
    primary_source = str(item_config.get("primary_source") or "").strip()
    if not series_id:
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"bls_series.{key}.series_id not configured",
        }
    return {
        "provider": "bls",
        "series_id": series_id,
        "name": item_config.get("name") or key,
        "asset_type": _asset_type_from_fred_series_config(key, config),
        "source_tier": item_config.get("source_tier") or "official_fallback",
        "primary_source": primary_source or _candidate_source_label(_fred_candidate(key, config)),
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": item_config.get("definition_note"),
    }


def _bea_candidate(key: str, config: dict) -> dict:
    item_config = _bea_config(config, key)
    table = str(item_config.get("table") or "").strip()
    line = str(item_config.get("line") or "").strip()
    primary_source = str(item_config.get("primary_source") or "").strip()
    if not table or not line:
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": "inflation",
            "error": f"bea_series.{key}.table or line not configured",
        }
    return {
        "provider": "bea",
        "series_key": key,
        "name": key,
        "asset_type": "inflation",
        "source_tier": item_config.get("source_tier") or "official_fallback",
        "primary_source": primary_source or "FRED",
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": item_config.get("definition_note"),
        "table": table,
        "line": line,
        "frequency": item_config.get("frequency"),
        "unit": item_config.get("unit"),
    }


def _call_provider(candidate: dict) -> dict:
    provider = candidate["provider"]

    if provider == "fred":
        return fred_provider.get_fred_latest(candidate["series_id"])

    if provider == "yfinance":
        return yfinance_provider.get_latest_price(candidate["symbol"])

    if provider == "bls":
        return bls_provider.get_latest_observation(
            str(candidate["series_id"]),
            primary_source=str(candidate.get("primary_source") or ""),
        )

    if provider == "bea":
        return bea_provider.get_latest_pce_price_index(str(candidate["series_key"]))

    if provider == "fedfunds":
        return fedfunds_provider.get_latest_effr()

    if provider == "treasury":
        return treasury_provider.get_par_yield(str(candidate["maturity"]))

    if provider == "manual":
        return _get_manual_market_item(candidate["key"], candidate["path"])

    if provider == "alpha_vantage":
        if candidate.get("mode") == "spot":
            return alpha_vantage_provider.get_gold_spot()
        return alpha_vantage_provider.get_gold_history_latest(
            interval=str(candidate.get("interval") or "daily")
        )

    return {
        "value": None,
        "source": candidate.get("source") or provider,
        "timestamp": _utc_now(),
        "status": "error",
        "error": candidate.get("error") or f"Unsupported provider: {provider}",
    }


def _treasury_yield_candidate(primary_series_id: str, maturity: str) -> dict:
    return {
        "provider": "treasury",
        "maturity": maturity,
        "name": f"U.S. Treasury {maturity} par yield",
        "asset_type": "interest_rate",
        "source_tier": "official_fallback",
        "primary_source": f"FRED:{primary_series_id}",
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": treasury_provider.DEFINITION_NOTE,
    }


def _fedfunds_candidate() -> dict:
    return {
        "provider": "fedfunds",
        "name": "New York Fed daily EFFR",
        "asset_type": "policy_rate",
        "source_tier": "official_fallback",
        "primary_source": fedfunds_provider.PRIMARY_SOURCE,
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "fallback_series": fedfunds_provider.FALLBACK_SERIES,
        "definition_note": fedfunds_provider.DEFINITION_NOTE,
        "frequency": "daily",
        "unit": "percent",
    }
