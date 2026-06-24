from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from datetime import date

from . import bea_provider, bls_provider, fred_provider, treasury_provider
from .market_data_service import (
    _optional_mapping,
    _to_float_or_none,
    _utc_now,
)


def _fred_financial_condition_item(
    *,
    key: str,
    series_id: str,
    timestamp: str,
    financial_config: dict,
) -> dict:
    result = fred_provider.get_fred_latest(series_id)
    attempt = {
        "source": result.get("source") or "FRED",
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp") or timestamp,
        "series_id": result.get("series_id") or series_id,
        "observation_date": result.get("observation_date"),
        "source_tier": financial_config.get("source_tier"),
    }

    value = _to_float_or_none(result.get("value"))
    if result.get("status") != "ok" or value is None:
        return _financial_condition_error(
            key=key,
            name=str(financial_config.get("name") or key),
            timestamp=result.get("timestamp") or timestamp,
            error=str(result.get("error") or "FRED financial condition request failed"),
            financial_config=financial_config,
            series_id=series_id,
            source=result.get("source") or "FRED",
            observation_date=result.get("observation_date"),
            attempted_sources=[attempt],
        )

    return {
        "key": key,
        "name": financial_config.get("name") or key,
        "value": value,
        "unit": financial_config.get("unit"),
        "observation_date": result.get("observation_date"),
        "source": result.get("source") or "FRED",
        "source_tier": financial_config.get("source_tier"),
        "freshness": "unknown",
        "status": "ok",
        "error": None,
        "interpretation_hint": financial_config.get("interpretation_hint"),
        "risk_relevance": financial_config.get("risk_relevance"),
        "asset_type": financial_config.get("asset_type"),
        "series_id": result.get("series_id") or series_id,
        "timestamp": result.get("timestamp") or timestamp,
        "attempted_sources": [attempt],
    }


def _package_item_from_config(
    *,
    key: str,
    item_config: dict,
    expected_frequency: str,
    max_stale_days: int,
    timestamp: str,
) -> dict:
    provider = str(item_config.get("provider") or "").strip().lower()
    if provider == "fred":
        return _fred_package_item(
            key=key,
            item_config=item_config,
            expected_frequency=expected_frequency,
            max_stale_days=max_stale_days,
            timestamp=timestamp,
        )
    if provider in {"not_available", "research_needed"}:
        return _package_unavailable_item(key, item_config, timestamp)
    return _package_item(
        key=key,
        name=str(item_config.get("name") or key),
        value=None,
        unit=item_config.get("unit"),
        observation_date=None,
        source="not_configured",
        source_tier=item_config.get("source_tier") or "not_available",
        freshness="not_available",
        status="not_configured",
        error=f"Unsupported provider for {key}: {provider or 'missing'}",
        interpretation_hint=item_config.get("interpretation_hint"),
        risk_relevance=item_config.get("risk_relevance"),
        timestamp=timestamp,
    )


def _bls_config(config: dict, key: str) -> dict:
    bls_series = _optional_mapping(config, "bls_series")
    item = bls_series.get(key)
    return item if isinstance(item, dict) else {}


def _bea_config(config: dict, key: str) -> dict:
    bea_series = _optional_mapping(config, "bea_series")
    item = bea_series.get(key)
    return item if isinstance(item, dict) else {}


def _fred_package_item(
    *,
    key: str,
    item_config: dict,
    expected_frequency: str,
    max_stale_days: int,
    timestamp: str,
) -> dict:
    series_id = str(item_config.get("series_id") or "").strip()
    name = str(item_config.get("name") or key)
    source = f"FRED:{series_id}" if series_id else "not_configured"
    if not series_id:
        return _package_item(
            key=key,
            name=name,
            value=None,
            unit=item_config.get("unit"),
            observation_date=None,
            source=source,
            source_tier=item_config.get("source_tier") or "not_available",
            freshness="not_available",
            status="not_configured",
            error=f"{key}.series_id not configured",
            interpretation_hint=item_config.get("interpretation_hint"),
            risk_relevance=item_config.get("risk_relevance"),
            timestamp=timestamp,
        )

    result = fred_provider.get_fred_latest(series_id)
    attempts = [_package_attempt(result, series_id, item_config)]
    value = _to_float_or_none(result.get("value"))
    if result.get("status") != "ok" or value is None:
        fallback_result = _official_fallback_for_fred_series(series_id)
        fallback_value = _to_float_or_none(fallback_result.get("value"))
        if fallback_result.get("status") == "ok" and fallback_value is not None:
            attempts.append(_package_attempt(fallback_result, series_id, item_config))
            observation_date = fallback_result.get("observation_date")
            return _package_item(
                key=key,
                name=name,
                value=fallback_value,
                unit=item_config.get("unit"),
                observation_date=observation_date,
                source=fallback_result.get("source"),
                source_tier=fallback_result.get("source_tier") or "official_fallback",
                freshness=_package_freshness(
                    observation_date,
                    expected_frequency=expected_frequency,
                    max_stale_days=max_stale_days,
                ),
                status="ok",
                error=None,
                interpretation_hint=item_config.get("interpretation_hint"),
                risk_relevance=item_config.get("risk_relevance"),
                timestamp=fallback_result.get("timestamp") or timestamp,
                attempted_sources=attempts,
                primary_source=source,
                fallback_used=True,
                fallback_reason="primary_source_unavailable",
                fallback_series=fallback_result.get("fallback_series"),
                source_series=fallback_result.get("fallback_series"),
                definition_note=fallback_result.get("definition_note"),
            )

        return _package_item(
            key=key,
            name=name,
            value=None,
            unit=item_config.get("unit"),
            observation_date=result.get("observation_date"),
            source=source,
            source_tier=item_config.get("source_tier") or "official_or_public_data_api",
            freshness="unknown",
            status="error",
            error=str(result.get("error") or "FRED request failed"),
            interpretation_hint=item_config.get("interpretation_hint"),
            risk_relevance=item_config.get("risk_relevance"),
            timestamp=result.get("timestamp") or timestamp,
            series_id=series_id,
            attempted_sources=attempts,
            primary_source=source,
            fallback_used=False,
        )

    observation_date = result.get("observation_date")
    return _package_item(
        key=key,
        name=name,
        value=value,
        unit=item_config.get("unit"),
        observation_date=observation_date,
        source=source,
        source_tier=item_config.get("source_tier") or "official_or_public_data_api",
        freshness=_package_freshness(
            observation_date,
            expected_frequency=expected_frequency,
            max_stale_days=max_stale_days,
        ),
        status="ok",
        error=None,
        interpretation_hint=item_config.get("interpretation_hint"),
        risk_relevance=item_config.get("risk_relevance"),
        timestamp=result.get("timestamp") or timestamp,
        series_id=series_id,
        attempted_sources=attempts,
        primary_source=source,
        fallback_used=False,
    )


def _package_unavailable_item(key: str, item_config: dict, timestamp: str) -> dict:
    status = str(item_config.get("status") or item_config.get("provider") or "not_available")
    if status not in {"not_available", "research_needed"}:
        status = "not_available"
    return _package_item(
        key=key,
        name=str(item_config.get("name") or key),
        value=None,
        unit=item_config.get("unit"),
        observation_date=None,
        source=status,
        source_tier=item_config.get("source_tier") or status,
        freshness=status,
        status=status,
        error=item_config.get("unavailable_reason") or f"{key} is {status}.",
        interpretation_hint=item_config.get("interpretation_hint"),
        risk_relevance=item_config.get("risk_relevance"),
        timestamp=timestamp,
    )


def _derived_package_error(
    key: str,
    source_item: dict,
    error: str,
    timestamp: str,
    *,
    unit: Any | None = None,
    window_days: int | None = None,
    calculation: str | None = None,
    status: str = "insufficient_history",
    freshness: str = "insufficient_history",
    interpretation_hint: str | None = None,
    **extra: Any,
) -> dict:
    return _package_item(
        key=key,
        name=key,
        value=None,
        unit=unit,
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=freshness,
        status=status,
        error=error,
        interpretation_hint=interpretation_hint,
        risk_relevance=None,
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=window_days,
        calculation=calculation,
        **extra,
    )


def _source_error_derived_item(
    key: str,
    source_item: dict,
    interpretation_hint: str,
    timestamp: str,
    *,
    unit: Any | None = None,
    window_days: int | None = None,
    calculation: str | None = None,
    **extra: Any,
) -> dict:
    source_error = str(source_item.get("error") or "Source data unavailable.")
    return _package_item(
        key=key,
        name=key,
        value=None,
        unit=unit,
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness") or "unknown",
        status="error",
        error=source_error,
        interpretation_hint=interpretation_hint,
        risk_relevance=None,
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=window_days,
        calculation=calculation,
        **extra,
    )


def _package_item(
    *,
    key: str,
    name: str,
    value: Any,
    unit: Any,
    observation_date: str | None,
    source: str | None,
    source_tier: str | None,
    freshness: str | None,
    status: str,
    error: str | None,
    interpretation_hint: str | None,
    risk_relevance: str | None,
    timestamp: str,
    series_id: str | None = None,
    attempted_sources: list[dict] | None = None,
    **extra: Any,
) -> dict:
    item = {
        "key": key,
        "name": name,
        "value": value,
        "unit": unit,
        "observation_date": observation_date,
        "source": source,
        "source_tier": source_tier,
        "freshness": freshness,
        "status": status,
        "error": error,
        "interpretation_hint": interpretation_hint,
        "risk_relevance": risk_relevance,
        "timestamp": timestamp,
        "attempted_sources": attempted_sources or [],
    }
    if series_id:
        item["series_id"] = series_id
    item.update({extra_key: extra_value for extra_key, extra_value in extra.items() if extra_value is not None})
    return item


def _package_attempt(result: dict, series_id: str, item_config: dict) -> dict:
    attempt = {
        "source": result.get("source") or "FRED",
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp"),
        "observation_date": result.get("observation_date"),
        "source_tier": result.get("source_tier") or item_config.get("source_tier"),
    }
    if result.get("series_id") or result.get("source") in {None, "FRED"}:
        attempt["series_id"] = result.get("series_id") or series_id
    if result.get("fallback_series"):
        attempt["fallback_series"] = result["fallback_series"]
    if result.get("definition_note"):
        attempt["definition_note"] = result["definition_note"]
    if result.get("unit"):
        attempt["unit"] = result["unit"]
    if result.get("bea_dataset"):
        attempt["bea_dataset"] = result["bea_dataset"]
    if result.get("table"):
        attempt["table"] = result["table"]
    if result.get("line"):
        attempt["line"] = result["line"]
    if result.get("frequency"):
        attempt["frequency"] = result["frequency"]
    return attempt


def _package_data_cutoff(*groups: dict[str, Any]) -> str | None:
    dates = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for item in group.values():
            if not isinstance(item, dict) or item.get("status") != "ok":
                continue
            observed_at = _parse_date(item.get("observation_date"))
            if observed_at:
                dates.append(observed_at)
    return max(dates).isoformat() if dates else None


def _package_freshness(
    observation_date: Any,
    *,
    expected_frequency: str,
    max_stale_days: int,
) -> str:
    observed_at = _parse_date(observation_date)
    if observed_at is None:
        return "unknown"
    today = datetime.now(timezone.utc).date()
    if expected_frequency == "monthly":
        month_gap = (today.year - observed_at.year) * 12 + today.month - observed_at.month
        if month_gap <= 2:
            return "normal_lag"
        if month_gap == 3:
            return "extended_lag"
        return "stale"
    return "fresh" if (today - observed_at).days <= max_stale_days else "stale"


def _financial_condition_config(key: str, config: dict) -> dict:
    financial_conditions = _optional_mapping(config, "financial_conditions")
    item = financial_conditions.get(key)
    return item if isinstance(item, dict) else {}


def _financial_condition_base(
    *,
    key: str,
    name: str,
    timestamp: str,
    status: str,
    error: str | None,
    financial_config: dict | None = None,
    series_id: str | None = None,
    source: str | None = None,
    observation_date: str | None = None,
    attempted_sources: list[dict] | None = None,
) -> dict:
    financial_config = financial_config if isinstance(financial_config, dict) else {}
    return {
        "key": key,
        "name": name,
        "value": None,
        "unit": financial_config.get("unit"),
        "observation_date": observation_date,
        "source": source or financial_config.get("source") or "not_configured",
        "source_tier": financial_config.get("source_tier") or "not_available",
        "freshness": "not_available" if status in {"not_available", "not_configured"} else "unknown",
        "status": status,
        "error": error,
        "interpretation_hint": financial_config.get("interpretation_hint"),
        "risk_relevance": financial_config.get("risk_relevance"),
        "asset_type": financial_config.get("asset_type"),
        "series_id": series_id or financial_config.get("series_id"),
        "timestamp": timestamp,
        "attempted_sources": attempted_sources or [],
    }


def _financial_condition_not_available(
    *,
    key: str,
    name: str,
    timestamp: str,
    financial_config: dict,
) -> dict:
    return _financial_condition_base(
        key=key,
        name=name,
        timestamp=timestamp,
        status="not_available",
        error=financial_config.get("unavailable_reason")
        or "Financial condition is not available from configured sources.",
        financial_config=financial_config,
        source="not_available",
    )


def _financial_condition_not_configured(
    *,
    key: str,
    name: str,
    timestamp: str,
    error: str,
    financial_config: dict | None = None,
) -> dict:
    return _financial_condition_base(
        key=key,
        name=name,
        timestamp=timestamp,
        status="not_configured",
        error=error,
        financial_config=financial_config,
        source="not_configured",
    )


def _financial_condition_error(
    *,
    key: str,
    name: str,
    timestamp: str,
    error: str,
    financial_config: dict,
    series_id: str | None = None,
    source: str | None = None,
    observation_date: str | None = None,
    attempted_sources: list[dict] | None = None,
) -> dict:
    return _financial_condition_base(
        key=key,
        name=name,
        timestamp=timestamp,
        status="error",
        error=error,
        financial_config=financial_config,
        series_id=series_id,
        source=source,
        observation_date=observation_date,
        attempted_sources=attempted_sources,
    )


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _official_fallback_for_fred_series(series_id: str) -> dict:
    bls_series_by_fred = {
        "CPIAUCSL": "CUSR0000SA0",
        "CPILFESL": "CUSR0000SA0L1E",
        "PAYEMS": "CES0000000001",
    }
    bls_series_id = bls_series_by_fred.get(series_id)
    if bls_series_id:
        return bls_provider.get_latest_observation(
            bls_series_id,
            primary_source=f"FRED:{series_id}",
        )

    bea_series_by_fred = {
        "PCEPI": "headline_pce",
        "PCEPILFE": "core_pce",
    }
    bea_series_key = bea_series_by_fred.get(series_id)
    if bea_series_key:
        return bea_provider.get_latest_pce_price_index(bea_series_key)

    maturity_by_series = {
        "DGS2": "2y",
        "DGS10": "10y",
        "DGS30": "30y",
    }
    maturity = maturity_by_series.get(series_id)
    if maturity:
        return treasury_provider.get_par_yield(maturity)

    return {
        "status": "not_configured",
        "error": f"No official fallback configured for {series_id}",
        "source": "official_fallback",
        "source_tier": "official_fallback",
        "timestamp": _utc_now(),
    }
