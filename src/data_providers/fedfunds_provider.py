from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


SOURCE = "New York Fed"
SOURCE_TIER = "official_fallback"
API_URL = "https://markets.newyorkfed.org/api/rates/all/search.json"
PRIMARY_SOURCE = "FRED:FEDFUNDS"
FALLBACK_SERIES = "NY Fed EFFR daily"
DEFINITION_NOTE = (
    "New York Fed official fallback; daily effective federal funds rate; "
    "not monthly FRED FEDFUNDS average."
)


def get_latest_effr() -> dict:
    generated_at = _utc_now()

    try:
        import requests
    except ImportError as exc:
        return _effr_error(f"requests import failed: {exc}", generated_at)

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=21)
    params = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "type": "EFFR",
    }

    try:
        response = requests.get(API_URL, params=params, timeout=20)
    except Exception as exc:
        return _effr_error(f"NY Fed EFFR request failed: {exc}", generated_at)

    if response.status_code != 200:
        return _effr_error(
            f"NY Fed EFFR HTTP status {response.status_code}: {_text_preview(response.text)}",
            generated_at,
        )

    try:
        payload = response.json()
    except ValueError:
        return _effr_error(
            f"NY Fed EFFR response was not JSON: {_text_preview(response.text)}",
            generated_at,
        )

    latest = _latest_effr_observation(payload)
    if latest is None:
        return _effr_error(
            "NY Fed EFFR response contained no parseable EFFR observation",
            generated_at,
        )

    observation_date, value, row = latest
    return {
        "key": "fedfunds",
        "value": value,
        "observation_date": observation_date,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "ok",
        "error": None,
        "timestamp": generated_at,
        "primary_source": PRIMARY_SOURCE,
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "fallback_series": FALLBACK_SERIES,
        "source_series": FALLBACK_SERIES,
        "definition_note": DEFINITION_NOTE,
        "frequency": "daily",
        "unit": "percent",
        "rate_type": "EFFR",
        "volume_in_billions": row.get("volumeInBillions"),
    }


def _latest_effr_observation(payload: dict) -> tuple[str, float, dict] | None:
    rows = payload.get("refRates")
    if not isinstance(rows, list):
        return None

    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "") != "EFFR":
            continue
        observation_date = str(row.get("effectiveDate") or "").strip()
        value = _to_float_or_none(row.get("percentRate"))
        if not observation_date or value is None:
            continue
        matches.append((observation_date, value, row))

    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1]


def _effr_error(error: str, timestamp: str) -> dict:
    return {
        "key": "fedfunds",
        "value": None,
        "observation_date": None,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "error",
        "error": error,
        "timestamp": timestamp,
        "primary_source": PRIMARY_SOURCE,
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "fallback_series": FALLBACK_SERIES,
        "source_series": FALLBACK_SERIES,
        "definition_note": DEFINITION_NOTE,
        "frequency": "daily",
        "unit": "percent",
    }


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


def _text_preview(text: str) -> str:
    return str(text).replace("\n", " ")[:200]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
