from __future__ import annotations

import importlib.util
from pathlib import Path

from data_providers import ofr_fsi_provider


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingest_ofr_fsi_download.py"
SPEC = importlib.util.spec_from_file_location("ingest_ofr_fsi_download", SCRIPT)
assert SPEC and SPEC.loader
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


def _fixture() -> bytes:
    return (
        "Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,"
        "United States,Other advanced economies,Emerging markets\n"
        "2026-06-17,1.2,0.2,0.1,0.3,0.2,0.4,0.8,0.3,0.1\n"
    ).encode()


def test_download_url_discovery_and_fallback():
    html = (
        '<form method="get" action="/financial-stress-index/data/fsi.csv">'
        "<button>Download all data</button></form>"
    )
    assert ofr_fsi_provider.discover_download_url(html) == (
        "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
    )
    assert ofr_fsi_provider.discover_download_url("<html></html>") is None


def test_parser_maps_total_components_and_regions():
    rows = ofr_fsi_provider.parse_fsi_csv(
        _fixture(), ingested_at="2026-06-19T00:00:00+00:00"
    )
    assert len(rows) == 9
    by_key = {row["metric_key"]: row for row in rows}
    assert by_key["ofr_fsi_total"]["value"] == 1.2
    assert by_key["ofr_fsi_equity_valuation"]["value"] == 0.1
    assert by_key["ofr_fsi_emerging_markets"]["value"] == 0.1


def test_source_badge_reference_only_and_model_boundary(tmp_path):
    path = tmp_path / "fsi.csv"
    path.write_bytes(_fixture())
    metadata = ofr_fsi_provider.load_csv_source(file_path=path)
    row = ofr_fsi_provider.parse_fsi_csv(
        metadata["content"], ingested_at=metadata["retrieved_at"]
    )[0]
    observation = ingest.build_market_observation(row, metadata=metadata)
    assert observation["source_badge"] == "official_reference"
    assert observation["lineage"]["trigger_eligibility"] == "reference_only"
    assert observation["lineage"]["model_boundary"] == [
        "D10_not_replaced",
        "D11_not_replaced",
    ]
    boundary = observation["lineage"]["interpretation_boundary"]
    assert "does not replace internal D10 or D11" in boundary


def test_fixture_ingest_writes_reference_rows(tmp_path):
    path = tmp_path / "fsi.csv"
    path.write_bytes(_fixture())
    summary = ingest.build_ingest_summary(
        file_path=path,
        db_path=tmp_path / "market.sqlite3",
        dry_run=False,
    )
    assert summary["normalized_observations"] == 9
    assert summary["inserted_count"] == 9
