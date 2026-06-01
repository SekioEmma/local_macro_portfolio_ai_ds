from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import ProviderHealthCheck, ProviderHealthResponse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HEALTH_PATH = PROJECT_ROOT / "outputs" / "reports" / "provider_health_check.json"
NEXT_ACTION = "python scripts/run_provider_health_check.py --save"
MAX_ERROR_SUMMARY_LENGTH = 200
COMPACT_CHECK_FIELDS = (
    "key",
    "provider",
    "status",
    "source",
    "observation_date",
    "value_present",
    "error_type",
    "error_summary",
)


def build_provider_health(health_path: Path | str | None = None) -> ProviderHealthResponse:
    path = Path(health_path) if health_path is not None else DEFAULT_HEALTH_PATH
    if not path.exists():
        return _not_run_yet()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ProviderHealthResponse(
            generated_at=None,
            overall_status="error",
            summary={},
            checks=[],
            next_action=NEXT_ACTION,
            error_summary="provider health cache is invalid or unreadable",
        )

    if not isinstance(payload, dict):
        return ProviderHealthResponse(
            generated_at=None,
            overall_status="error",
            summary={},
            checks=[],
            next_action=NEXT_ACTION,
            error_summary="provider health cache is invalid or unreadable",
        )

    return ProviderHealthResponse(
        generated_at=_optional_string(payload.get("generated_at")),
        overall_status=str(payload.get("overall_status") or "unknown"),
        summary=payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        checks=_compact_checks(payload.get("checks")),
    )


def _not_run_yet() -> ProviderHealthResponse:
    return ProviderHealthResponse(
        generated_at=None,
        overall_status="not_run_yet",
        summary={},
        checks=[],
        next_action=NEXT_ACTION,
        error_summary=None,
    )


def _compact_checks(value: Any) -> list[ProviderHealthCheck]:
    if not isinstance(value, list):
        return []

    checks = []
    for item in value:
        if not isinstance(item, dict):
            continue
        compact = {field: item.get(field) for field in COMPACT_CHECK_FIELDS}
        compact["key"] = str(compact.get("key") or "")
        compact["provider"] = str(compact.get("provider") or "")
        compact["status"] = str(compact.get("status") or "unknown")
        compact["source"] = _optional_string(compact.get("source"))
        compact["observation_date"] = _optional_string(compact.get("observation_date"))
        compact["value_present"] = _optional_bool(compact.get("value_present"))
        compact["error_type"] = _optional_string(compact.get("error_type"))
        compact["error_summary"] = _safe_error_summary(compact.get("error_summary"))
        checks.append(ProviderHealthCheck(**compact))
    return checks


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _safe_error_summary(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[redacted]", text)
    text = re.sub(
        r"(?i)(api[_-]?key|apikey|token|secret)=([^&\s]+)",
        r"\1=[redacted]",
        text,
    )
    if len(text) > MAX_ERROR_SUMMARY_LENGTH:
        return text[:MAX_ERROR_SUMMARY_LENGTH].rstrip()
    return text
