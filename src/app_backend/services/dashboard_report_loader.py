from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPORT_FILES = {
    "market_snapshot": "market_snapshot.json",
    "market_temperature": "market_temperature.json",
    "portfolio_snapshot": "portfolio_snapshot.json",
    "provider_health": "provider_health_check.json",
}
OPTIONAL_METADATA_REPORT_FILES = {
    "llm_context_pack": "llm_context_pack.json",
}


@dataclass(frozen=True)
class ReportState:
    name: str
    path: Path
    exists: bool
    data: dict[str, Any] | None = None
    error_summary: str | None = None


def load_report(name: str, path: Path) -> ReportState:
    if not path.exists():
        return ReportState(name=name, path=path, exists=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ReportState(
            name=name,
            path=path,
            exists=True,
            error_summary=f"{path.name} is invalid or unreadable",
        )
    if not isinstance(payload, dict):
        return ReportState(
            name=name,
            path=path,
            exists=True,
            error_summary=f"{path.name} is not a JSON object",
        )
    return ReportState(name=name, path=path, exists=True, data=payload)


def load_dashboard_reports(base_dir: Path) -> dict[str, ReportState]:
    reports = {
        key: load_report(key, base_dir / file_name)
        for key, file_name in REPORT_FILES.items()
    }
    for key, file_name in OPTIONAL_METADATA_REPORT_FILES.items():
        path = base_dir / file_name
        if path.exists():
            reports[key] = load_report(key, path)
    return reports
