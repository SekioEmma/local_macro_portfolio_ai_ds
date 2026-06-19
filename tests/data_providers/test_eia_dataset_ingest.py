from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from data_providers.source_registry import prefer_source


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingest_eia_controlled_dataset.py"
SPEC = importlib.util.spec_from_file_location("ingest_eia_controlled_dataset", SCRIPT)
assert SPEC and SPEC.loader
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


def test_dataset_parser_normalizes_schema():
    payload = (
        "period,series,value,units\n"
        "2026-06-17,RWTC,75.25,Dollars per Barrel\n"
        "2026-06-18,OTHER,90,Dollars per Barrel\n"
        "bad,RWTC,not-a-number,Dollars per Barrel\n"
    ).encode()
    rows = ingest.parse_eia_csv(
        payload,
        dataset_name="wti_spot",
        series_column="series",
    )
    assert rows == [
        {
            "metric_key": "wti_oil",
            "dataset_name": "wti_spot",
            "observation_date": "2026-06-17",
            "value": 75.25,
            "unit": "Dollars per Barrel",
        }
    ]


def test_local_file_hash_and_audit_metadata(tmp_path):
    path = tmp_path / "wti.csv"
    path.write_text("period,value\n2026-06-17,75.25\n", encoding="utf-8")
    metadata = ingest.load_controlled_dataset(file_path=path)
    assert metadata["retrieval_method"] == "local_file"
    assert len(metadata["file_hash"]) == 64
    row = ingest.parse_eia_csv(metadata["payload"], dataset_name="wti_spot")[0]
    observation = ingest.build_market_observation(
        row,
        metadata=metadata,
        ingested_at="2026-06-19T00:00:00+00:00",
    )
    assert observation["source_badge"] == "dataset_official"
    assert observation["raw_hash"] == metadata["file_hash"]
    assert observation["lineage"]["dataset_location"] == str(path.resolve())
    assert "price forecasts" in observation["lineage"]["interpretation_boundary"]


def test_controlled_download_rejects_non_eia_host():
    with pytest.raises(ValueError, match="eia_gov"):
        ingest.load_controlled_dataset(url="https://example.com/data.csv")


def test_energy_source_priority():
    assert prefer_source("dataset_official", "official_fallback") is True
    assert prefer_source("official_fallback", "commercial_api_fallback") is True
    assert prefer_source("commercial_api_fallback", "proxy") is True


def test_raw_eia_datasets_are_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/eia/*" in gitignore


def test_ingest_writes_normalized_rows(tmp_path):
    path = tmp_path / "brent.csv"
    path.write_text(
        "period,value\n2026-06-17,76.1\n2026-06-18,77.2\n",
        encoding="utf-8",
    )
    summary = ingest.build_ingest_summary(
        dataset_name="brent_spot",
        file_path=path,
        db_path=tmp_path / "market.sqlite3",
        dry_run=False,
    )
    assert summary["normalized_observations"] == 2
    assert summary["inserted_count"] == 2
