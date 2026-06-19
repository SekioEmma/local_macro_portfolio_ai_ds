from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .gdelt_registry import get_query_preset
from .gdelt_schema import (
    GdeltEventSummaryBucket,
    GdeltStorySummaryBucket,
    PROVIDER,
)


GDELT_BASE_URL = "https://gdeltcloud.com/api/v2"


def load_gdelt_api_key() -> str | None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return os.getenv("GDELT_CLOUD_API_KEY")
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv()
    return os.getenv("GDELT_CLOUD_API_KEY")


def build_summary_request(
    *,
    summary_kind: str,
    query_key: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    if summary_kind not in {"events", "stories"}:
        raise ValueError(f"unsupported_gdelt_summary_kind:{summary_kind}")
    validate_window(window_start, window_end)
    preset = get_query_preset(query_key)
    if preset.endpoint == "energy/assets":
        raise ValueError("energy_asset_preset_requires_energy_summary_endpoint")
    params = {
        **preset.params,
        "date_start": window_start,
        "date_end": window_end,
        "group_by": preset.group_by,
    }
    return {
        "url": f"{GDELT_BASE_URL}/{summary_kind}/summary",
        "params": params,
        "query_key": query_key,
        "group_by": preset.group_by,
    }


def validate_window(window_start: str, window_end: str) -> None:
    try:
        start = date.fromisoformat(window_start)
        end = date.fromisoformat(window_end)
    except ValueError as exc:
        raise ValueError("gdelt_window_must_use_iso_dates") from exc
    if start > end:
        raise ValueError("gdelt_window_start_after_end")
    if (end - start).days > 30:
        raise ValueError("gdelt_explicit_window_exceeds_30_days")


def fetch_summary(
    *,
    summary_kind: str,
    query_key: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    request = build_summary_request(
        summary_kind=summary_kind,
        query_key=query_key,
        window_start=window_start,
        window_end=window_end,
    )
    api_key = load_gdelt_api_key()
    if not api_key:
        return {
            "status": "not_available",
            "error": "GDELT_CLOUD_API_KEY not configured",
            **request,
        }
    try:
        import requests
    except ImportError as exc:
        return {"status": "error", "error": f"requests import failed:{exc}", **request}
    try:
        response = requests.get(
            request["url"],
            params=request["params"],
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=45,
        )
    except Exception as exc:
        return {
            "status": "error",
            "error": f"request_failed:{exc.__class__.__name__}",
            **request,
        }
    if response.status_code != 200:
        return {
            "status": "error",
            "error": f"http_status:{response.status_code}",
            "retry_after": response.headers.get("Retry-After"),
            **request,
        }
    try:
        payload = response.json()
    except ValueError:
        return {"status": "error", "error": "response_not_json", **request}
    if payload.get("success") is False:
        return {
            "status": "error",
            "error": str(payload.get("code") or payload.get("error") or "api_error"),
            **request,
        }
    return {
        "status": "ok",
        "payload": payload,
        "raw_payload_hash": canonical_payload_hash(payload),
        "retrieved_at": _utc_now(),
        **request,
    }


def normalize_event_summary(
    payload: dict[str, Any],
    *,
    query_key: str,
    window_start: str,
    window_end: str,
    ingested_at: str,
    raw_payload_hash: str | None = None,
) -> list[GdeltEventSummaryBucket]:
    payload_hash = raw_payload_hash or canonical_payload_hash(payload)
    group_by = str(payload.get("group_by") or get_query_preset(query_key).group_by)
    output = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        output.append(
            GdeltEventSummaryBucket(
                provider=PROVIDER,
                query_key=query_key,
                window_start=window_start,
                window_end=window_end,
                group_by=group_by,
                bucket_key=str(item.get("key") or ""),
                event_count=_int(item.get("event_count")),
                conflict_event_count=_int(item.get("conflict_event_count")),
                cameoplus_event_count=_int(item.get("cameoplus_event_count")),
                fatality_event_count=_int(item.get("fatality_event_count")),
                fatalities=_int(item.get("fatalities")),
                article_count=_int(item.get("article_count")),
                avg_significance=_number(
                    item.get("avg_significance")
                    if item.get("avg_significance") is not None
                    else _nested(metrics, "significance", "avg")
                ),
                max_significance=_number(
                    item.get("max_significance")
                    if item.get("max_significance") is not None
                    else _nested(metrics, "significance", "max")
                ),
                avg_goldstein_scale=_number(
                    item.get("avg_goldstein_scale")
                    if item.get("avg_goldstein_scale") is not None
                    else _nested(metrics, "goldstein_scale", "avg")
                ),
                avg_market_sensitivity=_number(
                    _nested(metrics, "cameoplus", "market_sensitivity", "avg")
                ),
                avg_confidence=_number(_nested(metrics, "confidence", "avg")),
                raw_payload_hash=payload_hash,
                ingested_at=ingested_at,
            )
        )
    return output


def normalize_story_summary(
    payload: dict[str, Any],
    *,
    query_key: str,
    window_start: str,
    window_end: str,
    ingested_at: str,
    raw_payload_hash: str | None = None,
) -> list[GdeltStorySummaryBucket]:
    payload_hash = raw_payload_hash or canonical_payload_hash(payload)
    group_by = str(payload.get("group_by") or get_query_preset(query_key).group_by)
    output = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        linked = metrics.get("linked_events") if isinstance(metrics.get("linked_events"), dict) else {}
        output.append(
            GdeltStorySummaryBucket(
                provider=PROVIDER,
                query_key=query_key,
                window_start=window_start,
                window_end=window_end,
                group_by=group_by,
                bucket_key=str(item.get("key") or ""),
                story_count=_int(item.get("story_count")),
                article_count=_int(item.get("article_count")),
                linked_event_count=_int(item.get("linked_event_count")),
                avg_significance=_number(
                    item.get("avg_significance")
                    if item.get("avg_significance") is not None
                    else _nested(metrics, "significance", "avg")
                ),
                max_significance=_number(
                    item.get("max_significance")
                    if item.get("max_significance") is not None
                    else _nested(metrics, "significance", "max")
                ),
                avg_linked_event_market_sensitivity=_number(
                    _nested(linked, "cameoplus", "market_sensitivity", "avg")
                ),
                avg_linked_event_goldstein_scale=_number(
                    _nested(linked, "goldstein_scale", "avg")
                ),
                avg_confidence=_number(_nested(linked, "confidence", "avg")),
                raw_payload_hash=payload_hash,
                ingested_at=ingested_at,
            )
        )
    return output


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nested(value: dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
