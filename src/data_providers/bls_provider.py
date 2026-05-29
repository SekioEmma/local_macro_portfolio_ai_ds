from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


SOURCE = "BLS"
SOURCE_TIER = "official_fallback"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

SERIES_METADATA = {
    "CUSR0000SA0": {
        "key": "cpi",
        "name": "CPI-U All Items",
        "unit": "index",
        "definition_note": (
            "BLS official fallback; not FRED; CPI-U all items, U.S. city average, "
            "seasonally adjusted monthly index."
        ),
    },
    "CUSR0000SA0L1E": {
        "key": "core_cpi",
        "name": "CPI-U All Items Less Food and Energy",
        "unit": "index",
        "definition_note": (
            "BLS official fallback; not FRED; CPI-U all items less food and energy, "
            "U.S. city average, seasonally adjusted monthly index."
        ),
    },
    "CES0000000001": {
        "key": "nonfarm",
        "name": "All Employees, Total Nonfarm",
        "unit": "thousands_of_persons",
        "definition_note": (
            "BLS official fallback; not FRED; Current Employment Statistics total nonfarm "
            "all employees, seasonally adjusted, thousands of persons."
        ),
    },
}


def get_latest_observation(series_id: str, *, primary_source: str) -> dict:
    generated_at = _utc_now()
    metadata = SERIES_METADATA.get(series_id, {})

    try:
        import requests
    except ImportError as exc:
        return _bls_error(
            series_id=series_id,
            error=f"requests import failed: {exc}",
            timestamp=generated_at,
            primary_source=primary_source,
        )

    body: dict[str, Any] = {
        "seriesid": [series_id],
        "startyear": str(datetime.now(timezone.utc).year - 1),
        "endyear": str(datetime.now(timezone.utc).year),
    }
    api_key = os.getenv("BLS_API_KEY")
    if api_key:
        body["registrationKey"] = api_key

    try:
        response = requests.post(BLS_API_URL, json=body, timeout=20)
    except Exception as exc:
        return _bls_error(
            series_id=series_id,
            error=f"BLS request failed: {exc}",
            timestamp=generated_at,
            primary_source=primary_source,
        )

    if response.status_code != 200:
        return _bls_error(
            series_id=series_id,
            error=f"BLS HTTP status {response.status_code}: {_text_preview(response.text)}",
            timestamp=generated_at,
            primary_source=primary_source,
        )

    try:
        payload = response.json()
    except ValueError:
        return _bls_error(
            series_id=series_id,
            error=f"BLS response was not JSON: {_text_preview(response.text)}",
            timestamp=generated_at,
            primary_source=primary_source,
        )

    if payload.get("status") != "REQUEST_SUCCEEDED":
        messages = payload.get("message")
        error = "; ".join(str(item) for item in messages) if isinstance(messages, list) else str(messages)
        return _bls_error(
            series_id=series_id,
            error=f"BLS API status {payload.get('status')}: {error}",
            timestamp=generated_at,
            primary_source=primary_source,
        )

    latest = _latest_monthly_observation(payload, series_id)
    if latest is None:
        return _bls_error(
            series_id=series_id,
            error="BLS response contained no parseable monthly observation",
            timestamp=generated_at,
            primary_source=primary_source,
        )

    observation_date, value, footnotes = latest
    return {
        "key": metadata.get("key"),
        "name": metadata.get("name") or series_id,
        "value": value,
        "unit": metadata.get("unit"),
        "observation_date": observation_date,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "ok",
        "error": None,
        "timestamp": generated_at,
        "series_id": series_id,
        "primary_source": primary_source,
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": metadata.get("definition_note"),
        "footnotes": footnotes,
    }


def _latest_monthly_observation(payload: dict, series_id: str) -> tuple[str, float, list[str]] | None:
    series_list = payload.get("Results", {}).get("series", [])
    if not isinstance(series_list, list):
        return None

    for series in series_list:
        if not isinstance(series, dict) or series.get("seriesID") != series_id:
            continue
        observations = series.get("data", [])
        if not isinstance(observations, list):
            continue
        for item in observations:
            if not isinstance(item, dict):
                continue
            period = str(item.get("period") or "")
            if period == "M13":
                continue
            if not period.startswith("M"):
                continue
            value = _to_float_or_none(item.get("value"))
            year = str(item.get("year") or "").strip()
            if value is None or not year:
                continue
            month = _period_to_month(period)
            if month is None:
                continue
            return (
                f"{year}-{month:02d}-01",
                value,
                _footnotes(item.get("footnotes")),
            )
    return None


def _period_to_month(period: str) -> int | None:
    try:
        month = int(period[1:])
    except ValueError:
        return None
    if 1 <= month <= 12:
        return month
    return None


def _footnotes(raw_footnotes: Any) -> list[str]:
    if not isinstance(raw_footnotes, list):
        return []
    notes = []
    for item in raw_footnotes:
        if isinstance(item, dict) and item.get("text"):
            notes.append(str(item["text"]))
    return notes


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _bls_error(series_id: str, error: str, timestamp: str, primary_source: str) -> dict:
    metadata = SERIES_METADATA.get(series_id, {})
    return {
        "key": metadata.get("key"),
        "name": metadata.get("name") or series_id,
        "value": None,
        "unit": metadata.get("unit"),
        "observation_date": None,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "error",
        "error": error,
        "timestamp": timestamp,
        "series_id": series_id,
        "primary_source": primary_source,
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": metadata.get("definition_note"),
    }


def _text_preview(text: str) -> str:
    return str(text).replace("\n", " ")[:200]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
