from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import market_history_store  # noqa: E402
from data_providers.source_registry import source_audit_metadata  # noqa: E402


EIA_DATASETS: dict[str, dict[str, Any]] = {
    "wti_spot": {
        "metric_key": "wti_oil",
        "unit": "USD_per_barrel",
        "identifiers": {"RWTC", "PET.RWTC.D", "wti_spot"},
    },
    "brent_spot": {
        "metric_key": "brent_oil",
        "unit": "USD_per_barrel",
        "identifiers": {"RBRTE", "PET.RBRTE.D", "brent_spot"},
    },
    "retail_gasoline": {
        "metric_key": "retail_gasoline",
        "unit": "USD_per_gallon",
        "identifiers": {
            "EMM_EPMR_PTE_NUS_DPG",
            "PET.EMM_EPMR_PTE_NUS_DPG.W",
            "retail_gasoline",
        },
    },
}


def load_controlled_dataset(
    *,
    file_path: Path | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    if bool(file_path) == bool(url):
        raise ValueError("provide_exactly_one_of_file_path_or_url")
    if file_path is not None:
        resolved = file_path.resolve()
        payload = resolved.read_bytes()
        modified = datetime.fromtimestamp(
            resolved.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        return {
            "payload": payload,
            "location": str(resolved),
            "retrieval_method": "local_file",
            "release_or_modified_at": modified,
            "file_hash": hashlib.sha256(payload).hexdigest(),
        }
    assert url is not None
    host = (urlparse(url).hostname or "").lower()
    if host != "eia.gov" and not host.endswith(".eia.gov"):
        raise ValueError("controlled_download_requires_eia_gov_host")
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(f"requests import failed:{exc}") from exc
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    payload = response.content
    return {
        "payload": payload,
        "location": url,
        "retrieval_method": "controlled_download",
        "release_or_modified_at": response.headers.get("Last-Modified"),
        "file_hash": hashlib.sha256(payload).hexdigest(),
    }


def parse_eia_csv(
    payload: bytes,
    *,
    dataset_name: str,
    date_column: str = "period",
    value_column: str = "value",
    series_column: str | None = None,
) -> list[dict[str, Any]]:
    if dataset_name not in EIA_DATASETS:
        raise ValueError(f"unsupported_eia_dataset:{dataset_name}")
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("eia_csv_missing_header")
    missing = {date_column, value_column} - set(reader.fieldnames)
    if missing:
        raise ValueError(f"eia_csv_missing_columns:{','.join(sorted(missing))}")
    config = EIA_DATASETS[dataset_name]
    records = []
    for row in reader:
        if series_column:
            identifier = str(row.get(series_column) or "").strip()
            if identifier not in config["identifiers"]:
                continue
        observation_date = _normalize_date(row.get(date_column))
        value = _to_float_or_none(row.get(value_column))
        if not observation_date or value is None:
            continue
        records.append(
            {
                "metric_key": config["metric_key"],
                "dataset_name": dataset_name,
                "observation_date": observation_date,
                "value": value,
                "unit": str(row.get("units") or config["unit"]),
            }
        )
    records.sort(key=lambda item: item["observation_date"])
    return records


def build_market_observation(
    row: dict[str, Any],
    *,
    metadata: dict[str, Any],
    ingested_at: str,
) -> dict[str, Any]:
    dataset_id = row["dataset_name"]
    audit = source_audit_metadata(
        "eia",
        source_series=dataset_id,
        retrieval_method=metadata["retrieval_method"],
        freshness_policy="dataset_release_controlled",
        ingested_at=ingested_at,
        extra={
            "dataset_name": dataset_id,
            "dataset_location": metadata["location"],
            "release_or_modified_at": metadata.get("release_or_modified_at"),
            "file_hash": metadata["file_hash"],
            "source_priority": "above_fred_alpha_vantage_yfinance",
            "allowed_contexts": [
                "inflation_energy_pressure",
                "energy_supply_context",
                "scenario_stress_support",
            ],
        },
    )
    return {
        "metric_key": row["metric_key"],
        "observation_date": row["observation_date"],
        "value": row["value"],
        "value_text": str(row["value"]),
        "unit": row["unit"],
        "status": "ok",
        "source": "EIA",
        "source_badge": "dataset_official",
        "provider": "eia",
        "source_series": dataset_id,
        "fetched_at": ingested_at,
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "raw",
        "lineage": audit,
        "raw_hash": metadata["file_hash"],
    }


def build_ingest_summary(
    *,
    dataset_name: str,
    file_path: Path | None = None,
    url: str | None = None,
    db_path: Path | str | None = None,
    date_column: str = "period",
    value_column: str = "value",
    series_column: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    metadata = load_controlled_dataset(file_path=file_path, url=url)
    records = parse_eia_csv(
        metadata["payload"],
        dataset_name=dataset_name,
        date_column=date_column,
        value_column=value_column,
        series_column=series_column,
    )
    ingested_at = _utc_now()
    summary = {
        "dataset_name": dataset_name,
        "retrieval_method": metadata["retrieval_method"],
        "dataset_location": metadata["location"],
        "file_hash": metadata["file_hash"],
        "normalized_observations": len(records),
        "inserted_count": 0,
        "updated_count": 0,
        "dry_run": dry_run,
    }
    for row in records:
        if dry_run:
            continue
        result = market_history_store.upsert_market_observation(
            build_market_observation(
                row, metadata=metadata, ingested_at=ingested_at
            ),
            db_path=db_path,
        )
        summary[f"{result['status']}_count"] += 1
    return summary


def _normalize_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (
        text[:10],
        f"{text}-01" if len(text) == 7 else "",
        f"{text}-01-01" if len(text) == 4 else "",
    ):
        if not candidate:
            continue
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            continue
    return None


def _to_float_or_none(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a controlled official EIA CSV dataset.")
    parser.add_argument("--dataset", required=True, choices=sorted(EIA_DATASETS))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--url")
    parser.add_argument("--date-column", default="period")
    parser.add_argument("--value-column", default="value")
    parser.add_argument("--series-column", default=None)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        dataset_name=args.dataset,
        file_path=args.file,
        url=args.url,
        db_path=args.db_path,
        date_column=args.date_column,
        value_column=args.value_column,
        series_column=args.series_column,
        dry_run=args.dry_run or not args.write,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
