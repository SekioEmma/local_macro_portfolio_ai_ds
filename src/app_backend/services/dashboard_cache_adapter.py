"""Adapter helpers between dashboard_service and the shared cache primitives.

These functions are pure: they take all path/state inputs as parameters and
return their results without touching module-level state. dashboard_service
wraps them with the module-level defaults (DEFAULT_REPORTS_DIR,
DEFAULT_MARKET_HISTORY_DB_PATH, PROJECT_REPORTS_DIR) so tests can continue
monkeypatching those defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app_backend.services.dashboard_cache_key import (
    build_dashboard_cache_key,
    cache_bypass_reason,
)
from app_backend.services.dashboard_report_loader import (
    OPTIONAL_METADATA_REPORT_FILES,
    REPORT_FILES,
)


DASHBOARD_CONTEXT_CACHE_SCHEMA_MARKER = "m11-dashboard-summary-evidence-cache-v1"


def resolved_path(path: Path | str) -> Path:
    target = Path(path).expanduser()
    try:
        return target.resolve(strict=False)
    except OSError:
        return target.absolute()


def same_path(left: Path | str, right: Path | str) -> bool:
    return resolved_path(left) == resolved_path(right)


def build_dashboard_cache_key_for_request(
    *,
    reports_dir: Path | str,
    market_history_db_path: Path | str,
):
    return build_dashboard_cache_key(
        reports_dir=reports_dir,
        market_history_db_path=market_history_db_path,
        required_report_files=REPORT_FILES,
        optional_report_files=OPTIONAL_METADATA_REPORT_FILES,
        schema_marker=DASHBOARD_CONTEXT_CACHE_SCHEMA_MARKER,
    )


def resolve_dashboard_market_history_db_path(
    reports_dir: Path,
    market_history_db_path: Path | str | None,
    *,
    default_market_history_db_path: Path | str,
    project_reports_dir: Path,
    current_default_provider: Callable[[], Path],
) -> Path | str:
    if market_history_db_path is not None:
        return market_history_db_path
    default_path = current_default_provider()
    if Path(default_market_history_db_path) != default_path:
        return default_market_history_db_path
    try:
        if reports_dir.resolve() == project_reports_dir.resolve():
            return default_market_history_db_path
    except OSError:
        pass
    return reports_dir / "market_history.sqlite3"


def shared_cache_bypass_reason(
    *,
    reports_dir: Path | str | None,
    base_dir: Path,
    market_history_db_path: Path | str | None,
    dashboard_market_history_db_path: Path | str,
    write_last_good: bool,
    default_reports_dir: Path,
    default_market_history_db_path_for_default_reports: Path | str,
) -> str | None:
    # Preserve the original conditional shape from dashboard_service; both
    # branches happen to compute the same value, but keeping the structure
    # makes the bypass-reason contract behavior-equivalent.
    if market_history_db_path is not None:
        market_history_default_check = same_path(
            dashboard_market_history_db_path,
            default_market_history_db_path_for_default_reports,
        )
    else:
        market_history_default_check = same_path(
            dashboard_market_history_db_path,
            default_market_history_db_path_for_default_reports,
        )
    return cache_bypass_reason(
        write_last_good=write_last_good,
        reports_dir_is_default=same_path(base_dir, default_reports_dir),
        market_history_db_path_is_default=market_history_default_check,
    )
