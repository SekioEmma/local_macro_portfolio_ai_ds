import ingest_official_ppifis_history as ingest
from data_quality import market_history_store


CONFIG_TEXT = """
deepseek_market_data_package:
  inflation_indicators:
    ppi_final_demand:
      provider: fred
      series_id: PPIFIS
      name: "Producer Price Index by Commodity: Final Demand"
      unit: index
      frequency: monthly
      source_tier: official_or_public_data_api
      interpretation_hint: "PPI Final Demand is distinct from PPIACO and not consensus surprise data."
"""


def test_official_ppifis_history_dry_run_does_not_fetch_or_write(tmp_path):
    config_path = tmp_path / "data_sources.yaml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        live=False,
        dry_run=True,
    )

    assert summary["configured_metrics"] == 1
    assert summary["enabled_metrics"] == ["ppi_final_demand"]
    assert summary["skipped_reasons"] == {"live_disabled": 1}
    assert summary["normalized_observations"] == 0
    assert not db_path.exists()


def test_official_ppifis_history_live_write_uses_existing_store(tmp_path):
    config_path = tmp_path / "data_sources.yaml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    db_path = tmp_path / "market_history.sqlite3"

    def fake_fetcher(series_id, limit):
        return {
            "status": "ok",
            "series_id": series_id,
            "timestamp": "2026-03-03T00:00:00+00:00",
            "data": [
                {"date": "2026-02-01", "value": "158.0"},
                {"date": "2026-01-01", "value": "157.0"},
            ],
        }

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        limit=2,
        live=True,
        dry_run=False,
        fetcher=fake_fetcher,
    )
    counts = market_history_store.count_observations_by_metric(db_path=db_path)
    rows = market_history_store.list_market_observations(
        metric_key="ppi_final_demand",
        db_path=db_path,
    )
    text = str(rows).lower()

    assert summary["normalized_observations"] == 2
    assert summary["inserted_count"] == 2
    assert summary["source_badge_distribution"] == {"official": 2}
    assert summary["source_series_distribution"] == {"PPIFIS": 2}
    assert counts == {"ppi_final_demand": 2}
    assert rows[0]["source"] == "FRED"
    assert rows[0]["source_badge"] == "official"
    assert rows[0]["source_series"] == "PPIFIS"
    assert rows[0]["metric_kind"] == "raw"
    assert "ppiaco" in str(rows[0]["lineage"]).lower()
    assert "raw_provider" not in text
    assert "api_key" not in text
    assert "holding" not in text
