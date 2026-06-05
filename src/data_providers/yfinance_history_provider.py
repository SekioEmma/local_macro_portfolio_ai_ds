from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable


SOURCE = "Yahoo Finance via yfinance"
PROVIDER = "yfinance"
ALLOWED_SOURCE_BADGES = {"unofficial_fallback", "proxy"}


def fetch_yfinance_batch_history(
    symbols: list[str],
    *,
    period: str = "6mo",
    interval: str = "1d",
    downloader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = _utc_now()
    if downloader is None:
        downloader = _default_yfinance_downloader
    try:
        raw_data = downloader(symbols=symbols, period=period, interval=interval)
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{exc.__class__.__name__}: {exc}",
            "raw_data": None,
            "generated_at": generated_at,
            "symbols": list(symbols),
            "period": period,
            "interval": interval,
        }
    return {
        "status": "ok",
        "error": None,
        "raw_data": raw_data,
        "generated_at": generated_at,
        "symbols": list(symbols),
        "period": period,
        "interval": interval,
    }


def normalize_yfinance_history(
    raw_data: Any,
    symbol_map: dict[str, dict[str, Any]],
    *,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    fetched = fetched_at or _utc_now()
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol, config in symbol_map.items():
        try:
            rows = _rows_for_symbol(raw_data, symbol)
        except (TypeError, ValueError) as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
            continue
        for row in rows:
            record = _normalize_row(symbol, config, row, fetched)
            if record is not None:
                records.append(record)
    return {
        "status": "ok" if records or not errors else "error",
        "records": records,
        "errors": errors,
        "record_count": len(records),
    }


def build_market_observations_from_yfinance(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in records:
        observations.append(
            {
                "metric_key": record["metric_key"],
                "observation_date": record["observation_date"],
                "value": record["value"],
                "value_text": record["value_text"],
                "unit": record.get("unit"),
                "status": "ok",
                "source": SOURCE,
                "source_badge": record["source_badge"],
                "provider": PROVIDER,
                "source_series": record["symbol"],
                "generated_at": record["fetched_at"],
                "fetched_at": record["fetched_at"],
                "freshness_status": "historical",
                "ai_context_allowed": False,
                "metric_kind": record["metric_kind"],
                "lineage": {
                    "symbol": record["symbol"],
                    "source_badge": record["source_badge"],
                    "value_field": record["value_field"],
                    "interpretation_hint": record["interpretation_hint"],
                },
                "raw_hash": record.get("raw_hash"),
            }
        )
    return observations


def load_yfinance_history_config(path: Path | str) -> dict[str, dict[str, Any]]:
    import yaml

    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    section = payload.get("yfinance_history", payload)
    symbol_map: dict[str, dict[str, Any]] = {}
    for group_name, items in section.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if not item.get("enabled", True):
                continue
            symbol = str(item.get("symbol") or "").strip()
            metric_key = str(item.get("metric_key") or "").strip()
            source_badge = str(item.get("source_badge") or "").strip()
            if not symbol or not metric_key or source_badge not in ALLOWED_SOURCE_BADGES:
                continue
            symbol_map[symbol] = {
                **item,
                "group": group_name,
                "symbol": symbol,
                "metric_key": metric_key,
                "source_badge": source_badge,
            }
    return symbol_map


def _normalize_row(
    symbol: str,
    config: dict[str, Any],
    row: dict[str, Any],
    fetched_at: str,
) -> dict[str, Any] | None:
    observation_date = _date_text(row.get("date") or row.get("Date") or row.get("index"))
    if not observation_date:
        return None
    value, value_field = _price_value(row)
    if value is None:
        return None
    source_badge = str(config.get("source_badge"))
    metric_kind = str(config.get("metric_kind") or ("proxy" if source_badge == "proxy" else "index"))
    hint = str(config.get("interpretation_hint") or "")
    if value_field == "Close" and "Adjusted Close" not in hint:
        hint = f"{hint} Close used because Adjusted Close was unavailable.".strip()
    return {
        "metric_key": str(config["metric_key"]),
        "symbol": symbol,
        "display_name": config.get("display_name"),
        "observation_date": observation_date,
        "value": value,
        "value_text": f"{value:.4f}",
        "unit": config.get("unit"),
        "source": SOURCE,
        "source_badge": source_badge,
        "provider": PROVIDER,
        "source_series": symbol,
        "fetched_at": fetched_at,
        "freshness_status": "historical",
        "metric_kind": metric_kind,
        "interpretation_hint": hint,
        "value_field": value_field,
        "raw_hash": None,
    }


def _price_value(row: dict[str, Any]) -> tuple[float | None, str | None]:
    for field in ("Adj Close", "Adjusted Close", "adj_close", "Close", "close"):
        if field not in row:
            continue
        value = row.get(field)
        if _is_number(value):
            return float(value), "Adjusted Close" if field in {"Adj Close", "Adjusted Close", "adj_close"} else "Close"
    return None, None


def _rows_for_symbol(raw_data: Any, symbol: str) -> list[dict[str, Any]]:
    if raw_data is None:
        return []
    if isinstance(raw_data, dict):
        if symbol in raw_data:
            return _coerce_rows(raw_data[symbol])
        return _coerce_rows(raw_data)
    if hasattr(raw_data, "empty"):
        return _dataframe_rows(raw_data, symbol)
    raise TypeError("unsupported yfinance raw data shape")


def _coerce_rows(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if "rows" in data:
            return _coerce_rows(data["rows"])
        return [dict(data)]
    if hasattr(data, "empty"):
        return _dataframe_rows(data, None)
    raise ValueError("malformed symbol history data")


def _dataframe_rows(dataframe: Any, symbol: str | None) -> list[dict[str, Any]]:
    if getattr(dataframe, "empty", False):
        return []
    frame = dataframe
    if symbol is not None and hasattr(frame, "xs"):
        try:
            if hasattr(frame, "columns") and getattr(frame.columns, "nlevels", 1) > 1:
                frame = _select_symbol_frame(frame, symbol)
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        payload = row.to_dict()
        payload["date"] = index
        rows.append(payload)
    return rows


def _select_symbol_frame(frame: Any, symbol: str) -> Any:
    columns = getattr(frame, "columns", None)
    if columns is None or getattr(columns, "nlevels", 1) <= 1:
        return frame
    for level in range(columns.nlevels):
        try:
            if symbol in set(columns.get_level_values(level)):
                return frame.xs(symbol, axis=1, level=level, drop_level=True)
        except Exception:
            continue
    return frame


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _is_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _default_yfinance_downloader(
    *,
    symbols: list[str],
    period: str,
    interval: str,
) -> Any:
    import yfinance as yf

    return yf.download(
        tickers=list(symbols),
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=False,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
