from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BEA_API_URL = "https://apps.bea.gov/api/data"
BEA_DATASET = "NIPA"
BEA_NIPA_MAPPINGS: dict[str, dict[str, Any]] = {
    "headline_pce_yoy": {
        "table": "T20804",
        "line": "1",
        "frequency": "M",
        "source_metric_key": "headline_pce_index",
        "unit": "percent_yoy",
        "line_description_tokens": ("personal consumption expenditures",),
        "transform": "yoy",
    },
    "core_pce_yoy": {
        "table": "T20804",
        "line": "25",
        "frequency": "M",
        "source_metric_key": "core_pce_index",
        "unit": "percent_yoy",
        "line_description_tokens": ("excluding food and energy",),
        "transform": "yoy",
    },
    "real_gdp_qoq_saaar": {
        "table": "T10101",
        "line": "1",
        "frequency": "Q",
        "source_metric_key": None,
        "unit": "percent_saaar",
        "line_description_tokens": ("gross domestic product",),
        "transform": "identity",
    },
}


def load_bea_api_key() -> str | None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return os.getenv("BEA_API_KEY")
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv()
    return os.getenv("BEA_API_KEY")


def build_bea_getdata_params(
    *,
    api_key: str,
    table: str,
    frequency: str,
    year: str = "X",
) -> dict[str, str]:
    return {
        "UserID": api_key,
        "method": "GETDATA",
        "datasetname": BEA_DATASET,
        "TableName": table,
        "Frequency": frequency,
        "Year": year,
        "ResultFormat": "JSON",
    }


def build_bea_discovery_params(*, api_key: str) -> dict[str, str]:
    return {
        "UserID": api_key,
        "method": "GETPARAMETERVALUES",
        "datasetname": BEA_DATASET,
        "ParameterName": "TableName",
        "ResultFormat": "JSON",
    }


def request_bea(params: dict[str, str]) -> dict[str, Any]:
    try:
        import requests
    except ImportError as exc:
        return {"status": "error", "error": f"requests import failed:{exc}", "data": []}
    try:
        response = requests.get(BEA_API_URL, params=params, timeout=45)
    except Exception as exc:
        return {
            "status": "error",
            "error": f"request_failed:{exc.__class__.__name__}",
            "data": [],
        }
    if response.status_code != 200:
        return {"status": "error", "error": f"http_status:{response.status_code}", "data": []}
    try:
        payload = response.json()
    except ValueError:
        return {"status": "error", "error": "response_not_json", "data": []}
    beaapi = payload.get("BEAAPI", {})
    results = beaapi.get("Results", {}) if isinstance(beaapi, dict) else {}
    error = beaapi.get("Error") if isinstance(beaapi, dict) else None
    if not error and isinstance(results, dict):
        error = results.get("Error")
    if error:
        if isinstance(error, dict):
            message = error.get("APIErrorDescription") or error.get("ErrorDetail") or "api_error"
        else:
            message = "api_error"
        return {"status": "error", "error": str(message), "data": []}
    return {"status": "ok", "payload": payload, "retrieved_at": _utc_now()}


def normalize_discovery(payload: dict[str, Any]) -> list[dict[str, str]]:
    results = payload.get("BEAAPI", {}).get("Results", {})
    candidates: Any = []
    if isinstance(results, dict):
        candidates = (
            results.get("ParamValue")
            or results.get("ParameterValues")
            or results.get("Data")
            or []
        )
    if not isinstance(candidates, list):
        return []
    normalized = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        table = str(
            item.get("TableName")
            or item.get("Key")
            or item.get("Table")
            or ""
        ).strip()
        description = str(
            item.get("Description")
            or item.get("Desc")
            or item.get("TableDescription")
            or ""
        ).strip()
        if table:
            normalized.append({"table": table, "description": description})
    return sorted(normalized, key=lambda item: item["table"])


def normalize_table_rows(
    payload: dict[str, Any],
    *,
    metric_key: str,
    ingested_at: str,
) -> list[dict[str, Any]]:
    mapping = BEA_NIPA_MAPPINGS[metric_key]
    rows = payload.get("BEAAPI", {}).get("Results", {}).get("Data", [])
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("TableName") or "") != mapping["table"]:
            continue
        if str(row.get("LineNumber") or "") != mapping["line"]:
            continue
        period = str(row.get("TimePeriod") or "")
        observation_date = _period_start(period, mapping["frequency"])
        value = _to_float_or_none(row.get("DataValue"))
        if not observation_date or value is None:
            continue
        _validate_row_metadata(row, mapping)
        normalized.append(
            {
                "metric_key": metric_key,
                "source_metric_key": mapping["source_metric_key"],
                "observation_date": observation_date,
                "value": value,
                "table": mapping["table"],
                "line": mapping["line"],
                "frequency": mapping["frequency"],
                "unit": mapping["unit"],
                "transform": mapping["transform"],
                "line_description": str(row.get("LineDescription") or ""),
                "series_code": str(row.get("SeriesCode") or ""),
                "ingested_at": ingested_at,
            }
        )
    normalized.sort(key=lambda item: item["observation_date"])
    return normalized


def calculate_bea_metric(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    if rows[0]["transform"] == "identity":
        return [dict(row) for row in rows]
    dated = {row["observation_date"]: row for row in rows}
    output = []
    for observation_date, row in sorted(dated.items()):
        year, month, _ = (int(part) for part in observation_date.split("-"))
        prior_date = f"{year - 1:04d}-{month:02d}-01"
        prior = dated.get(prior_date)
        if not prior or float(prior["value"]) == 0:
            continue
        output.append(
            {
                **row,
                "value": (float(row["value"]) / float(prior["value"]) - 1.0) * 100.0,
                "prior_observation_date": prior_date,
            }
        )
    return output


def _validate_row_metadata(row: dict[str, Any], mapping: dict[str, Any]) -> None:
    description = str(row.get("LineDescription") or "").lower()
    missing = [
        token
        for token in mapping["line_description_tokens"]
        if token not in description
    ]
    if missing:
        raise ValueError(
            f"bea_line_description_mismatch:{mapping['table']}:{mapping['line']}"
        )
    time_period = str(row.get("TimePeriod") or "")
    if mapping["frequency"] not in time_period:
        raise ValueError(f"bea_frequency_mismatch:{time_period}")


def _period_start(value: str, frequency: str) -> str | None:
    if frequency == "M" and len(value) == 7 and "M" in value:
        year, month_text = value.split("M", 1)
        if year.isdigit() and month_text.isdigit() and 1 <= int(month_text) <= 12:
            return f"{year}-{int(month_text):02d}-01"
    if frequency == "Q" and len(value) == 6 and "Q" in value:
        year, quarter_text = value.split("Q", 1)
        if year.isdigit() and quarter_text.isdigit() and 1 <= int(quarter_text) <= 4:
            month = (int(quarter_text) - 1) * 3 + 1
            return f"{year}-{month:02d}-01"
    return None


def _to_float_or_none(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"---", "(NA)"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
