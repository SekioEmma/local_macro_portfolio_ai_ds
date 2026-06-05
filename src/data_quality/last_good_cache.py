from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAST_GOOD_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "last_good"

USABLE_STATUSES = {"ok", "watch", "pressure", "stress"}
BLOCKED_SOURCE_BADGES = {"missing", "research_needed", "search-derived", "proxy"}
SAFE_METRIC_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")
DAILY_KEY_MARKERS = (
    "dgs",
    "dfii",
    "t10yie",
    "vix",
    "spread",
    "sp500",
    "nasdaq",
    "wti",
    "brent",
)
MONTHLY_KEY_MARKERS = ("cpi", "pce", "ppi", "ppiaco")
SAFE_FIELDS = (
    "metric_key",
    "value",
    "value_text",
    "unit",
    "status",
    "source",
    "source_badge",
    "provider",
    "source_series",
    "observation_date",
    "generated_at",
    "fetched_at",
    "freshness_status",
    "ttl_policy",
    "ttl_days",
    "stale_after",
    "last_live_status",
    "last_error",
    "raw_hash",
)


def sanitize_metric_key(metric_key: str) -> str:
    text = str(metric_key or "").strip()
    if not text:
        raise ValueError("metric_key is required")
    if "/" in text or "\\" in text or ".." in text:
        raise ValueError("metric_key must not contain path traversal")
    safe = SAFE_METRIC_KEY_RE.sub("_", text).strip("._-").lower()
    if not safe:
        raise ValueError("metric_key has no safe filename characters")
    return safe[:120]


def save_last_good(
    metric: Any,
    *,
    cache_dir: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    candidate = _last_good_payload(metric, now=_normalize_now(now))
    if not _is_saveable(candidate):
        return {
            "saved": False,
            "status": "skipped",
            "reason": _skip_reason(candidate),
            "metric_key": candidate.get("metric_key"),
        }

    path = _metric_path(candidate["metric_key"], cache_dir=cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "saved": True,
        "status": "saved",
        "metric_key": candidate["metric_key"],
        "path": str(path),
    }


def load_last_good(
    metric_key: str,
    *,
    cache_dir: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = _metric_path(metric_key, cache_dir=cache_dir)
    if not path.exists():
        return {
            "status": "unavailable",
            "metric_key": metric_key,
            "metric": None,
            "error_summary": None,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {
            "status": "error",
            "metric_key": metric_key,
            "metric": None,
            "error_summary": f"last-good cache is unreadable: {exc.__class__.__name__}",
        }
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "metric_key": metric_key,
            "metric": None,
            "error_summary": "last-good cache is not a JSON object",
        }

    status = classify_last_good_status(payload, now=_normalize_now(now))
    return {
        "status": status,
        "metric_key": payload.get("metric_key") or metric_key,
        "metric": {key: payload.get(key) for key in SAFE_FIELDS if key in payload},
        "error_summary": None,
    }


def is_last_good_usable(metric: dict[str, Any], now: datetime | None = None) -> bool:
    return classify_last_good_status(metric, now=_normalize_now(now)) == "usable"


def classify_last_good_status(
    metric: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> str:
    if not metric:
        return "unavailable"
    if not _is_saveable(metric):
        return "error"

    checked_at = _normalize_now(now)
    fetched_at = _parse_datetime(metric.get("fetched_at"))
    stale_after = _parse_datetime(metric.get("stale_after"))
    ttl_days = metric.get("ttl_days")

    if fetched_at is None:
        return "error"
    if stale_after is None or not isinstance(ttl_days, int) or ttl_days <= 0:
        return "stale"
    if checked_at <= stale_after:
        return "usable"
    if checked_at <= stale_after + timedelta(days=ttl_days):
        return "stale"
    return "expired"


def list_last_good_cache(
    *,
    cache_dir: Path | str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    base_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_LAST_GOOD_CACHE_DIR
    if not base_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(base_dir.glob("*.json")):
        results.append(load_last_good(path.stem, cache_dir=base_dir, now=now))
    return results


def _last_good_payload(metric: Any, *, now: datetime) -> dict[str, Any]:
    metric_key = _field(metric, "metric_key")
    fetched_at = _isoformat(now)
    ttl_policy, ttl_days = _ttl_policy(str(metric_key or ""), _field(metric, "source_series"))
    stale_after = _isoformat(now + timedelta(days=ttl_days)) if ttl_days else None
    payload = {
        "metric_key": metric_key,
        "value": _field(metric, "value"),
        "value_text": _field(metric, "value_text"),
        "unit": _field(metric, "unit"),
        "status": _field(metric, "status"),
        "source": _field(metric, "source"),
        "source_badge": _field(metric, "source_badge"),
        "provider": _field(metric, "provider") or _field(metric, "source"),
        "source_series": _field(metric, "source_series"),
        "observation_date": _field(metric, "observation_date"),
        "generated_at": _field(metric, "generated_at"),
        "fetched_at": fetched_at,
        "freshness_status": _field(metric, "freshness_status"),
        "ttl_policy": ttl_policy,
        "ttl_days": ttl_days,
        "stale_after": stale_after,
        "last_live_status": _field(metric, "last_live_status") or _field(metric, "status"),
        "last_error": _field(metric, "last_error"),
        "raw_hash": None,
    }
    payload["metric_key"] = sanitize_metric_key(str(metric_key)) if metric_key else None
    payload["raw_hash"] = _safe_payload_hash(payload)
    return payload


def _is_saveable(metric: dict[str, Any]) -> bool:
    return (
        bool(metric.get("metric_key"))
        and metric.get("value") is not None
        and metric.get("status") in USABLE_STATUSES
        and metric.get("source_badge") not in BLOCKED_SOURCE_BADGES
        and bool(metric.get("observation_date") or metric.get("generated_at"))
    )


def _skip_reason(metric: dict[str, Any]) -> str:
    if not metric.get("metric_key"):
        return "metric_key_missing"
    if metric.get("value") is None:
        return "value_missing"
    if metric.get("status") not in USABLE_STATUSES:
        return f"status_{metric.get('status') or 'missing'}"
    if metric.get("source_badge") in BLOCKED_SOURCE_BADGES:
        return f"source_badge_{metric.get('source_badge')}"
    if not (metric.get("observation_date") or metric.get("generated_at")):
        return "date_missing"
    return "not_eligible"


def _metric_path(metric_key: str, *, cache_dir: Path | str | None) -> Path:
    base_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_LAST_GOOD_CACHE_DIR
    return base_dir / f"{sanitize_metric_key(metric_key)}.json"


def _ttl_policy(metric_key: str, source_series: Any) -> tuple[str, int | None]:
    text = f"{metric_key} {source_series or ''}".lower()
    if any(marker in text for marker in MONTHLY_KEY_MARKERS):
        return "monthly", 75
    if any(marker in text for marker in DAILY_KEY_MARKERS):
        return "daily", 7
    return "unknown", None


def _field(metric: Any, name: str) -> Any:
    if isinstance(metric, dict):
        return metric.get(name)
    return getattr(metric, name, None)


def _safe_payload_hash(payload: dict[str, Any]) -> str:
    safe_payload = {key: value for key, value in payload.items() if key != "raw_hash"}
    data = json.dumps(safe_payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _normalize_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
