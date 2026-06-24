from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_manual_market_data(path: str) -> dict:
    manual_path = _resolve_path(path)
    if not manual_path.exists():
        return {}

    rows_by_key: dict[str, dict] = {}
    try:
        with manual_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                key = str(row.get("key") or "").strip()
                if not key:
                    continue

                raw_value = row.get("value")
                value = _to_float_or_none(raw_value)
                status = "ok"
                error = None
                if value is None:
                    status = "error"
                    error = f"Manual market data value is not numeric: {raw_value}"

                updated_at = str(row.get("updated_at") or "").strip()
                rows_by_key[key] = {
                    "key": key,
                    "name": str(row.get("name") or key).strip(),
                    "value": value,
                    "currency": str(row.get("currency") or "").strip() or None,
                    "source": "manual",
                    "observation_date": str(row.get("observation_date") or "").strip()
                    or None,
                    "updated_at": updated_at or None,
                    "timestamp": updated_at or _utc_now(),
                    "status": status,
                    "error": error,
                    "notes": str(row.get("notes") or "").strip() or None,
                }
    except OSError as exc:
        return {
            "__file__": {
                "key": "__file__",
                "name": str(manual_path),
                "value": None,
                "currency": None,
                "source": "manual",
                "observation_date": None,
                "updated_at": None,
                "timestamp": _utc_now(),
                "status": "error",
                "error": f"Manual market data file could not be read: {exc}",
                "notes": None,
            }
        }

    return rows_by_key


def _candidate_source_label(candidate: dict) -> str:
    if candidate.get("primary_source"):
        return str(candidate["primary_source"])
    if candidate.get("provider") == "fred" and candidate.get("series_id"):
        return f"FRED:{candidate['series_id']}"
    if candidate.get("provider") == "treasury":
        return "U.S. Treasury"
    return str(candidate.get("source") or candidate.get("provider") or "unknown")


def _get_manual_market_item(key: str, path: str) -> dict:
    timestamp = _utc_now()
    manual_path = _resolve_path(path)
    if not manual_path.exists():
        return {
            "key": key,
            "value": None,
            "currency": None,
            "source": "manual",
            "timestamp": timestamp,
            "observation_date": None,
            "updated_at": None,
            "status": "missing",
            "error": "manual market data file not found",
            "path": str(manual_path),
        }

    manual_data = load_manual_market_data(path)
    file_error = manual_data.get("__file__")
    if isinstance(file_error, dict):
        return {**file_error, "key": key, "path": str(manual_path)}

    item = manual_data.get(key)
    if not isinstance(item, dict):
        return {
            "key": key,
            "value": None,
            "currency": None,
            "source": "manual",
            "timestamp": timestamp,
            "observation_date": None,
            "updated_at": None,
            "status": "error",
            "error": f"manual market data key not found: {key}",
            "path": str(manual_path),
        }

    return {**item, "path": str(manual_path)}


def _asset_type_from_market_symbols(key: str, config: dict) -> str | None:
    market_symbols = _optional_mapping(config, "market_symbols")
    symbol_config = market_symbols.get(key)
    if isinstance(symbol_config, dict) and symbol_config.get("asset_type"):
        return str(symbol_config["asset_type"])
    return None


def _asset_type_from_fred_series_config(key: str, config: dict) -> str | None:
    fred_series = _optional_mapping(config, "fred_series")
    series_config = fred_series.get(key)
    if isinstance(series_config, dict) and series_config.get("asset_type"):
        return str(series_config["asset_type"])
    return None


def _resolve_path(path: str) -> Path:
    requested_path = Path(path)
    if requested_path.is_absolute():
        return requested_path

    if requested_path.exists():
        return requested_path

    return _project_root() / requested_path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _optional_mapping(source: dict, key: str) -> dict:
    value = source.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"data_sources.yaml must contain mapping: {key}")
    return value


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
