from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "data_sources.yaml"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import fred_provider  # noqa: E402
from data_quality import liquidity_funding_stress  # noqa: E402
from data_quality import market_history_store  # noqa: E402


DEFAULT_LIMIT = 1600


def build_ingest_summary(
    *,
    config_path: Path | str | None = None,
    db_path: Path | str | None = None,
    dry_run: bool = True,
    live: bool = False,
    limit: int = DEFAULT_LIMIT,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    planned, missing = liquidity_funding_stress.planned_source_mappings(config_path)
    planned_official = {
        key: item
        for key, item in planned.items()
        if item.get("source_badge") == "official"
    }
    planned_reference = {
        key: item
        for key, item in planned.items()
        if item.get("source_badge") in {"official_fallback"}
    }
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "live": live,
        "write": bool(live and not dry_run),
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
        "planned_official_series": planned_official,
        "planned_reference_indices": planned_reference,
        "missing_source_mappings": missing,
        "required_flags_for_fetch": "--live",
        "required_flags_for_write": "--live --write",
        "fetched_series_count": 0,
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "source_badge_distribution": {},
        "provider_status": {},
        "derived_observations": 0,
    }
    if not live:
        _record_skip(summary, "live_disabled", len(planned))
        return summary

    fetched = fetch_and_normalize(planned, limit=limit, fetcher=fetcher)
    observations = fetched["observations"]
    summary["fetched_series_count"] = fetched["fetched_series_count"]
    summary["provider_status"] = fetched["provider_status"]
    summary["normalized_observations"] = len(observations)
    for error in fetched["errors"]:
        _record_skip(summary, error)
    for observation in observations:
        _count_badge(summary, observation["source_badge"])
        if dry_run:
            continue
        _write_observation(summary, observation, db_path=db_path)
    if not dry_run:
        derived = build_derived_history_observations(db_path=db_path)
        summary["derived_observations"] = len(derived)
        for observation in derived:
            _count_badge(summary, observation["source_badge"])
            _write_observation(summary, observation, db_path=db_path)
    return summary


def fetch_and_normalize(
    mappings: dict[str, dict[str, Any]],
    *,
    limit: int,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_fetcher = fetcher or fred_provider.get_fred_series
    fetched_at = _utc_now()
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    provider_status: dict[str, str] = {}
    for metric_key, item in sorted(mappings.items()):
        series_id = str(item["source_series"]).strip().upper()
        payload = active_fetcher(series_id, limit)
        status = str(payload.get("status") or "unknown")
        provider_status[metric_key] = status
        if status != "ok":
            errors.append(f"fetch_error:{metric_key}")
            continue
        for row in payload.get("data", []):
            value = _to_float_or_none(row.get("value"))
            observation_date = _text_or_none(row.get("date"))
            if value is None or observation_date is None:
                continue
            observations.append(
                {
                    "metric_key": metric_key,
                    "observation_date": observation_date,
                    "value": value,
                    "value_text": str(value),
                    "unit": item.get("unit"),
                    "status": "ok",
                    "source": item.get("source") or "FRED",
                    "source_badge": item["source_badge"],
                    "provider": "FRED",
                    "source_series": series_id,
                    "generated_at": payload.get("timestamp") or fetched_at,
                    "fetched_at": fetched_at,
                    "freshness_status": "historical",
                    "ai_context_allowed": item["source_badge"] in {"official", "official_fallback"},
                    "metric_kind": "raw",
                    "lineage": {
                        "provider": "FRED",
                        "source_series": series_id,
                        "source_detail": "Liquidity/funding reference history normalized observation.",
                    },
                }
            )
    return {
        "fetched_series_count": len(mappings),
        "observations": observations,
        "errors": errors,
        "provider_status": provider_status,
    }


def build_derived_history_observations(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    rows = liquidity_funding_stress.build_liquidity_funding_rows(db_path=db_path)
    observations: list[dict[str, Any]] = []
    for row in rows:
        if row["metric_key"] not in liquidity_funding_stress.DERIVED_METRIC_KEYS:
            continue
        if row["metric_key"] == "liquidity_funding_interpretation_boundary":
            continue
        if row["status"] not in {"ok", "watch", "pressure", "stress"}:
            continue
        if row["value"] is None:
            continue
        observations.append(
            {
                "metric_key": row["metric_key"],
                "observation_date": row["observation_date"] or _utc_now()[:10],
                "value": row["value"],
                "value_text": row["value_text"],
                "unit": row["unit"],
                "status": row["status"],
                "source": "local_market_history",
                "source_badge": "derived",
                "provider": "local_market_history",
                "source_series": row["source_series"] or row["metric_key"],
                "generated_at": row["generated_at"],
                "fetched_at": _utc_now(),
                "freshness_status": "historical",
                "ai_context_allowed": False,
                "metric_kind": "derived",
                "lineage": {
                    "calculation": row.get("interpretation_hint"),
                    "dependency_keys": row.get("missing_inputs") or [],
                    "input_evidence": row.get("input_evidence") or [],
                    "alignment": (row.get("component_contributions") or {}).get("alignment"),
                },
            }
        )
    return observations


def _write_observation(
    summary: dict[str, Any],
    observation: dict[str, Any],
    *,
    db_path: Path | str | None,
) -> None:
    try:
        result = market_history_store.upsert_market_observation(observation, db_path=db_path)
    except market_history_store.MarketHistoryValidationError as exc:
        _record_skip(summary, str(exc))
        return
    if result["status"] == "inserted":
        summary["inserted_count"] += 1
    elif result["status"] == "updated":
        summary["updated_count"] += 1


def _record_skip(summary: dict[str, Any], reason: str, count: int = 1) -> None:
    if count <= 0:
        return
    summary["skipped_count"] += count
    summary["skipped_reasons"][reason] = summary["skipped_reasons"].get(reason, 0) + count


def _count_badge(summary: dict[str, Any], badge: str) -> None:
    summary["source_badge_distribution"][badge] = summary["source_badge_distribution"].get(badge, 0) + 1


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or ingest liquidity/funding reference history into local market_history."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without fetching or writing.")
    parser.add_argument("--live", action="store_true", help="Allow live official/reference provider fetch.")
    parser.add_argument("--write", action="store_true", help="Write normalized observations.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True
    summary = build_ingest_summary(
        config_path=args.config,
        db_path=args.db_path,
        dry_run=dry_run,
        live=args.live,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
