from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import market_history_store  # noqa: E402
from data_providers.source_registry import source_audit_metadata  # noqa: E402


BLS_V1_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_CPI_SERIES: dict[str, dict[str, Any]] = {
    "CUSR0000SA0": {
        "index_metric_key": "headline_cpi_index",
        "yoy_metric_key": "headline_cpi_yoy",
        "expected_title_tokens": ("all items", "u.s. city average"),
    },
    "CUSR0000SA0L1E": {
        "index_metric_key": "core_cpi_index",
        "yoy_metric_key": "core_cpi_yoy",
        "expected_title_tokens": ("less food and energy", "u.s. city average"),
    },
}


def split_year_chunks(start_year: int, end_year: int, size: int = 10) -> list[tuple[int, int]]:
    if start_year > end_year:
        raise ValueError("start_year_must_not_exceed_end_year")
    if size < 1 or size > 10:
        raise ValueError("bls_v1_chunk_size_must_be_1_to_10")
    chunks = []
    cursor = start_year
    while cursor <= end_year:
        chunk_end = min(cursor + size - 1, end_year)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return chunks


def build_bls_v1_post_payload(
    series_ids: list[str], start_year: int, end_year: int
) -> dict[str, Any]:
    if end_year - start_year + 1 > 10:
        raise ValueError("bls_v1_window_exceeds_10_years")
    unknown = sorted(set(series_ids) - set(BLS_CPI_SERIES))
    if unknown:
        raise ValueError(f"unsupported_bls_series:{','.join(unknown)}")
    return {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
        "catalog": True,
    }


def fetch_bls_v1_window(
    series_ids: list[str], start_year: int, end_year: int
) -> dict[str, Any]:
    try:
        import requests
    except ImportError as exc:
        return {"status": "error", "error": f"requests import failed:{exc}", "series": []}
    payload = build_bls_v1_post_payload(series_ids, start_year, end_year)
    try:
        response = requests.post(BLS_V1_URL, json=payload, timeout=30)
    except Exception as exc:
        return {"status": "error", "error": f"request_failed:{exc.__class__.__name__}", "series": []}
    if response.status_code != 200:
        return {"status": "error", "error": f"http_status:{response.status_code}", "series": []}
    try:
        body = response.json()
    except ValueError:
        return {"status": "error", "error": "response_not_json", "series": []}
    if body.get("status") != "REQUEST_SUCCEEDED":
        return {
            "status": "error",
            "error": ";".join(str(item) for item in body.get("message", [])),
            "series": [],
        }
    return {
        "status": "ok",
        "series": body.get("Results", {}).get("series", []),
        "retrieved_at": _utc_now(),
    }


def validate_series_title(series_id: str, series_payload: dict[str, Any]) -> str:
    if series_id not in BLS_CPI_SERIES:
        raise ValueError(f"unsupported_bls_series:{series_id}")
    returned_id = str(series_payload.get("seriesID") or "")
    if returned_id != series_id:
        raise ValueError(f"bls_series_id_mismatch:{returned_id}")
    catalog = series_payload.get("catalog")
    title = ""
    if isinstance(catalog, dict):
        title = str(catalog.get("series_title") or catalog.get("seriesTitle") or "")
    if not title:
        title = str(series_payload.get("seriesTitle") or "")
    if title:
        lowered = title.lower()
        missing = [
            token
            for token in BLS_CPI_SERIES[series_id]["expected_title_tokens"]
            if token not in lowered
        ]
        if missing:
            raise ValueError(f"bls_series_title_mismatch:{series_id}:{','.join(missing)}")
        return "response_title_confirmed"
    return "series_registry_confirmed_response_id"


def normalize_bls_series(
    series_payload: dict[str, Any], *, ingested_at: str
) -> list[dict[str, Any]]:
    series_id = str(series_payload.get("seriesID") or "")
    title_validation = validate_series_title(series_id, series_payload)
    config = BLS_CPI_SERIES[series_id]
    records: list[dict[str, Any]] = []
    for item in series_payload.get("data", []):
        period = str(item.get("period") or "")
        year = str(item.get("year") or "")
        if period == "M13" or not period.startswith("M") or not year.isdigit():
            continue
        try:
            month = int(period[1:])
            value = float(str(item.get("value") or "").replace(",", ""))
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        records.append(
            {
                "series_id": series_id,
                "metric_key": config["index_metric_key"],
                "observation_date": f"{year}-{month:02d}-01",
                "value": value,
                "title_validation": title_validation,
                "ingested_at": ingested_at,
            }
        )
    records.sort(key=lambda item: item["observation_date"])
    return records


def calculate_yoy(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_series: dict[str, dict[str, dict[str, Any]]] = {}
    for row in records:
        by_series.setdefault(row["series_id"], {})[row["observation_date"]] = row
    output: list[dict[str, Any]] = []
    for series_id, dated in by_series.items():
        for observation_date, row in sorted(dated.items()):
            year, month, _ = (int(part) for part in observation_date.split("-"))
            prior_date = f"{year - 1:04d}-{month:02d}-01"
            prior = dated.get(prior_date)
            if not prior or float(prior["value"]) == 0:
                continue
            output.append(
                {
                    **row,
                    "metric_key": BLS_CPI_SERIES[series_id]["yoy_metric_key"],
                    "value": (float(row["value"]) / float(prior["value"]) - 1.0) * 100.0,
                    "prior_observation_date": prior_date,
                }
            )
    return output


def build_market_observation(row: dict[str, Any], *, derived: bool) -> dict[str, Any]:
    audit = source_audit_metadata(
        "bls",
        source_series=row["series_id"],
        retrieval_method="api_v1_post",
        freshness_policy="monthly_release",
        ingested_at=row["ingested_at"],
        extra={
            "title_validation": row["title_validation"],
            "source_priority": "primary_over_fred",
        },
    )
    if derived:
        audit["derivation"] = "year_over_year_percent_change"
        audit["prior_observation_date"] = row["prior_observation_date"]
    return {
        "metric_key": row["metric_key"],
        "observation_date": row["observation_date"],
        "value": row["value"],
        "value_text": f"{row['value']:.4f}" if derived else str(row["value"]),
        "unit": "percent_yoy" if derived else "index",
        "status": "ok",
        "source": "BLS",
        "source_badge": "official",
        "provider": "bls",
        "source_series": row["series_id"],
        "fetched_at": row["ingested_at"],
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "derived" if derived else "raw",
        "lineage": audit,
    }


def build_ingest_summary(
    *,
    start_year: int = 2000,
    end_year: int | None = None,
    db_path: Path | str | None = None,
    dry_run: bool = True,
    live: bool = False,
    fetcher: Callable[[list[str], int, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    final_year = end_year or date.today().year
    chunks = split_year_chunks(start_year, final_year)
    summary: dict[str, Any] = {
        "year_chunks": chunks,
        "series_ids": list(BLS_CPI_SERIES),
        "index_observations": 0,
        "derived_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "errors": [],
        "dry_run": dry_run,
        "live": live,
    }
    if not live:
        summary["errors"].append("live_disabled")
        return summary
    active_fetcher = fetcher or fetch_bls_v1_window
    all_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for chunk_start, chunk_end in chunks:
        result = active_fetcher(list(BLS_CPI_SERIES), chunk_start, chunk_end)
        if result.get("status") != "ok":
            summary["errors"].append(
                f"{chunk_start}-{chunk_end}:{result.get('error') or 'fetch_failed'}"
            )
            continue
        ingested_at = str(result.get("retrieved_at") or _utc_now())
        for series_payload in result.get("series", []):
            try:
                normalized = normalize_bls_series(
                    series_payload, ingested_at=ingested_at
                )
            except ValueError as exc:
                summary["errors"].append(str(exc))
                continue
            for row in normalized:
                all_rows[(row["series_id"], row["observation_date"])] = row
    index_rows = sorted(
        all_rows.values(), key=lambda item: (item["series_id"], item["observation_date"])
    )
    yoy_rows = calculate_yoy(index_rows)
    summary["index_observations"] = len(index_rows)
    summary["derived_observations"] = len(yoy_rows)
    observations = [
        build_market_observation(row, derived=derived)
        for row, derived in [(row, False) for row in index_rows] + [
        (row, True) for row in yoy_rows
        ]
    ]
    if not dry_run:
        write_result = market_history_store.upsert_market_observations(
            observations, db_path=db_path
        )
        summary["inserted_count"] = write_result["inserted_count"]
        summary["updated_count"] = write_result["updated_count"]
    return summary


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest official BLS CPI history via public API v1.")
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        start_year=args.start_year,
        end_year=args.end_year,
        db_path=args.db_path,
        dry_run=args.dry_run or not args.write,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
