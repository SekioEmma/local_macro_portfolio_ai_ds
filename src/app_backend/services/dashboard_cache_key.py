from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


CACHE_KEY_VERSION = "m11-dashboard-cache-key-v1"


@dataclass(frozen=True)
class FileSignature:
    path: str
    exists: bool
    size_bytes: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class DashboardCacheKey:
    version: str
    reports_dir: str
    market_history_db_path: str
    required_reports: tuple[FileSignature, ...]
    optional_reports: tuple[FileSignature, ...]
    market_history_db: FileSignature
    schema_marker: str
    digest: str


def resolve_path_for_key(path: Path | str) -> str:
    target = Path(path).expanduser()
    try:
        return str(target.resolve(strict=False))
    except OSError:
        return str(target.absolute())


def file_signature(path: Path | str) -> FileSignature:
    target = Path(path).expanduser()
    resolved = resolve_path_for_key(target)
    try:
        stat_result = target.stat()
    except OSError:
        return FileSignature(
            path=resolved,
            exists=False,
            size_bytes=None,
            mtime_ns=None,
        )

    size_bytes = stat_result.st_size if target.is_file() else None
    return FileSignature(
        path=resolved,
        exists=True,
        size_bytes=size_bytes,
        mtime_ns=stat_result.st_mtime_ns,
    )


def build_dashboard_cache_key(
    *,
    reports_dir: Path | str,
    market_history_db_path: Path | str,
    required_report_files: Mapping[str, str],
    optional_report_files: Mapping[str, str] | None = None,
    schema_marker: str = CACHE_KEY_VERSION,
) -> DashboardCacheKey:
    resolved_reports_dir = resolve_path_for_key(reports_dir)
    resolved_market_history_db_path = resolve_path_for_key(market_history_db_path)
    reports_path = Path(reports_dir).expanduser()

    required_reports = tuple(
        file_signature(reports_path / required_report_files[key])
        for key in sorted(required_report_files)
    )
    optional_files = optional_report_files or {}
    optional_reports = tuple(
        file_signature(reports_path / optional_files[key])
        for key in sorted(optional_files)
    )
    market_history_db = file_signature(market_history_db_path)

    key_without_digest = DashboardCacheKey(
        version=CACHE_KEY_VERSION,
        reports_dir=resolved_reports_dir,
        market_history_db_path=resolved_market_history_db_path,
        required_reports=required_reports,
        optional_reports=optional_reports,
        market_history_db=market_history_db,
        schema_marker=schema_marker,
        digest="",
    )
    digest = cache_key_digest(cache_key_payload(key_without_digest))
    return DashboardCacheKey(
        version=CACHE_KEY_VERSION,
        reports_dir=resolved_reports_dir,
        market_history_db_path=resolved_market_history_db_path,
        required_reports=required_reports,
        optional_reports=optional_reports,
        market_history_db=market_history_db,
        schema_marker=schema_marker,
        digest=digest,
    )


def cache_key_payload(key: DashboardCacheKey) -> dict[str, object]:
    return {
        "version": key.version,
        "reports_dir": key.reports_dir,
        "market_history_db_path": key.market_history_db_path,
        "required_reports": tuple(asdict(signature) for signature in key.required_reports),
        "optional_reports": tuple(asdict(signature) for signature in key.optional_reports),
        "market_history_db": asdict(key.market_history_db),
        "schema_marker": key.schema_marker,
    }


def cache_key_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cache_bypass_reason(
    *,
    write_last_good: bool,
    reports_dir_is_default: bool,
    market_history_db_path_is_default: bool,
) -> str | None:
    if write_last_good:
        return "cache_bypassed_for_write_last_good"
    if not reports_dir_is_default or not market_history_db_path_is_default:
        return "cache_bypassed_for_custom_path"
    return None
