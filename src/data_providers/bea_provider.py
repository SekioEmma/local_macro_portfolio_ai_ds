from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE = "BEA"
SOURCE_TIER = "official_fallback"
BEA_API_URL = "https://apps.bea.gov/api/data"
DATASET = "NIPA"

SERIES_METADATA = {
    "headline_pce": {
        "key": "pce",
        "bea_dataset": DATASET,
        "table": "T20804",
        "line": "1",
        "frequency": "M",
        "unit": "index_2017_100",
        "line_description": "Personal consumption expenditures (PCE)",
        "metric_name": "Fisher Price Index",
        "primary_source": "FRED:PCEPI",
        "definition_note": (
            "BEA official fallback; not FRED; NIPA Table 2.8.4 line 1, "
            "Personal consumption expenditures (PCE), monthly Fisher price index, "
            "index level 2017=100."
        ),
    },
    "core_pce": {
        "key": "core_pce",
        "bea_dataset": DATASET,
        "table": "T20804",
        "line": "25",
        "frequency": "M",
        "unit": "index_2017_100",
        "line_description": "PCE excluding food and energy",
        "metric_name": "Fisher Price Index",
        "primary_source": "FRED:PCEPILFE",
        "definition_note": (
            "BEA official fallback; not FRED; NIPA Table 2.8.4 line 25, "
            "PCE excluding food and energy, monthly Fisher price index, "
            "index level 2017=100."
        ),
    },
}


def get_latest_pce_price_index(series_key: str) -> dict:
    generated_at = _utc_now()
    metadata = SERIES_METADATA.get(series_key)
    if metadata is None:
        return _bea_error(
            metadata={},
            error=f"Unsupported BEA PCE series key: {series_key}",
            timestamp=generated_at,
        )

    api_key = _load_bea_api_key()
    if not api_key:
        return _bea_error(
            metadata=metadata,
            error="BEA_API_KEY not configured",
            timestamp=generated_at,
            status="not_available",
        )

    try:
        import requests
    except ImportError as exc:
        return _bea_error(
            metadata=metadata,
            error=f"requests import failed: {exc}",
            timestamp=generated_at,
        )

    params = {
        "UserID": api_key,
        "method": "GETDATA",
        "datasetname": metadata["bea_dataset"],
        "TableName": metadata["table"],
        "Frequency": metadata["frequency"],
        "Year": "X",
        "ResultFormat": "JSON",
    }

    try:
        response = requests.get(BEA_API_URL, params=params, timeout=30)
    except Exception as exc:
        return _bea_error(
            metadata=metadata,
            error=f"BEA request failed: {exc.__class__.__name__}",
            timestamp=generated_at,
        )

    if response.status_code != 200:
        return _bea_error(
            metadata=metadata,
            error=f"BEA HTTP status {response.status_code}: {_safe_preview(response.text, api_key)}",
            timestamp=generated_at,
        )

    try:
        payload = response.json()
    except ValueError:
        return _bea_error(
            metadata=metadata,
            error=f"BEA response was not JSON: {_safe_preview(response.text, api_key)}",
            timestamp=generated_at,
        )

    api_error = _bea_api_error(payload)
    if api_error:
        return _bea_error(
            metadata=metadata,
            error=_redact(api_error, api_key),
            timestamp=generated_at,
        )

    latest = _latest_matching_row(payload, metadata)
    if latest is None:
        return _bea_error(
            metadata=metadata,
            error="BEA response contained no matching PCE price-index row",
            timestamp=generated_at,
        )

    observation_date, value, row = latest
    metadata_mismatch = _metadata_mismatch(row, metadata)
    if metadata_mismatch:
        return _bea_error(
            metadata=metadata,
            error=metadata_mismatch,
            timestamp=generated_at,
        )

    return {
        "key": metadata["key"],
        "value": value,
        "observation_date": observation_date,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "ok",
        "error": None,
        "timestamp": generated_at,
        "bea_dataset": metadata["bea_dataset"],
        "table": metadata["table"],
        "line": metadata["line"],
        "frequency": metadata["frequency"],
        "unit": metadata["unit"],
        "primary_source": metadata["primary_source"],
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": metadata["definition_note"],
        "line_description": row.get("LineDescription"),
        "metric_name": row.get("METRIC_NAME"),
        "series_code": row.get("SeriesCode"),
    }


def _latest_matching_row(payload: dict, metadata: dict) -> tuple[str, float, dict] | None:
    rows = payload.get("BEAAPI", {}).get("Results", {}).get("Data", [])
    if not isinstance(rows, list):
        return None

    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("TableName") or "") != metadata["table"]:
            continue
        if str(row.get("LineNumber") or "") != metadata["line"]:
            continue
        if str(row.get("TimePeriod") or "")[-3:-2] != "M":
            continue
        value = _to_float_or_none(row.get("DataValue"))
        observation_date = _time_period_to_month_start(row.get("TimePeriod"))
        if value is None or observation_date is None:
            continue
        matches.append((observation_date, value, row))

    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1]


def _metadata_mismatch(row: dict, metadata: dict) -> str | None:
    checks = {
        "METRIC_NAME": metadata["metric_name"],
        "CL_UNIT": "Level",
    }
    for field, expected in checks.items():
        actual = str(row.get(field) or "")
        if actual != expected:
            return f"BEA metadata mismatch for {field}: expected {expected}, got {actual or 'missing'}"

    line_description = str(row.get("LineDescription") or "")
    if line_description != metadata["line_description"]:
        return (
            "BEA metadata mismatch for LineDescription: "
            f"expected {metadata['line_description']}, got {line_description or 'missing'}"
        )
    return None


def _bea_api_error(payload: dict) -> str | None:
    beaapi = payload.get("BEAAPI", {})
    if not isinstance(beaapi, dict):
        return "BEA response missing BEAAPI payload"
    error = beaapi.get("Error")
    if isinstance(error, dict):
        return str(error.get("APIErrorDescription") or error.get("ErrorDetail") or error)
    return None


def _time_period_to_month_start(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) != 7 or "M" not in text:
        return None
    year, month_text = text.split("M", 1)
    try:
        month = int(month_text)
    except ValueError:
        return None
    if not year.isdigit() or not 1 <= month <= 12:
        return None
    return f"{year}-{month:02d}-01"


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


def _bea_error(
    *,
    metadata: dict,
    error: str,
    timestamp: str,
    status: str = "error",
) -> dict:
    return {
        "key": metadata.get("key"),
        "value": None,
        "observation_date": None,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": status,
        "error": error,
        "timestamp": timestamp,
        "bea_dataset": metadata.get("bea_dataset"),
        "table": metadata.get("table"),
        "line": metadata.get("line"),
        "frequency": metadata.get("frequency"),
        "unit": metadata.get("unit"),
        "primary_source": metadata.get("primary_source"),
        "fallback_used": True,
        "fallback_reason": "primary_source_unavailable",
        "definition_note": metadata.get("definition_note"),
    }


def _load_bea_api_key() -> str | None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return os.getenv("BEA_API_KEY")

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv()
    return os.getenv("BEA_API_KEY")


def _safe_preview(text: str, api_key: str | None) -> str:
    return _redact(str(text).replace("\n", " ")[:200], api_key)


def _redact(text: str, api_key: str | None) -> str:
    if api_key:
        return text.replace(api_key, "[REDACTED]")
    return text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
