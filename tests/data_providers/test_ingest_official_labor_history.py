import ingest_official_labor_history as ingest
from data_providers import market_history_store


CONFIG_TEXT = """
deepseek_market_data_package:
  labor_indicators:
    unemployment_rate:
      provider: fred
      series_id: UNRATE
      name: "Unemployment Rate"
      unit: percent
      frequency: monthly
      source_tier: official_or_public_data_api
    initial_jobless_claims:
      provider: fred
      series_id: ICSA
      name: "Initial Claims"
      unit: claims
      frequency: weekly
      source_tier: official_or_public_data_api
    nonfarm_payrolls:
      provider: fred
      series_id: PAYEMS
      name: "All Employees, Total Nonfarm"
      unit: thousand persons
      frequency: monthly
      source_tier: official_or_public_data_api
    continuing_claims:
      provider: fred
      series_id: CCSA
      name: "Continued Claims"
      unit: claims
      frequency: weekly
      source_tier: official_or_public_data_api
"""


def test_official_labor_history_dry_run_does_not_fetch_or_write(tmp_path):
    config_path = tmp_path / "data_sources.yaml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    db_path = tmp_path / "market_history.sqlite3"
    calls = []

    def fake_fetcher(series_id, limit):
        calls.append((series_id, limit))
        raise AssertionError("dry-run must not fetch")

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        live=False,
        dry_run=True,
        fetcher=fake_fetcher,
    )

    assert summary["configured_metrics"] == 4
    assert summary["enabled_metrics"] == [
        "continuing_claims",
        "initial_jobless_claims",
        "nonfarm_payrolls",
        "unemployment_rate",
    ]
    assert summary["skipped_reasons"] == {"live_disabled": 4}
    assert summary["normalized_observations"] == 0
    assert summary["limits_by_metric"]["unemployment_rate"] == 24
    assert summary["limits_by_metric"]["nonfarm_payrolls"] == 24
    assert summary["limits_by_metric"]["initial_jobless_claims"] == 52
    assert summary["limits_by_metric"]["continuing_claims"] == 52
    assert calls == []
    assert not db_path.exists()


def test_official_labor_history_live_write_uses_normalized_observations(tmp_path):
    config_path = tmp_path / "data_sources.yaml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    db_path = tmp_path / "market_history.sqlite3"
    calls = []

    def fake_fetcher(series_id, limit):
        calls.append((series_id, limit))
        return {
            "status": "ok",
            "series_id": series_id,
            "timestamp": "2026-03-03T00:00:00+00:00",
            "data": [
                {"date": "2026-02-01", "value": "2.0"},
                {"date": "2026-01-01", "value": "1.0"},
            ],
            "provider_payload": {"must": "not persist"},
        }

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        live=True,
        dry_run=False,
        fetcher=fake_fetcher,
    )
    counts = market_history_store.count_observations_by_metric(db_path=db_path)
    all_rows = market_history_store.list_market_observations(db_path=db_path, limit=20)
    rows_by_metric = {
        metric_key: market_history_store.list_market_observations(metric_key=metric_key, db_path=db_path)
        for metric_key in counts
    }
    text = str(all_rows).lower()

    assert summary["normalized_observations"] == 8
    assert summary["inserted_count"] == 8
    assert summary["source_badge_distribution"] == {"official": 8}
    assert summary["source_series_distribution"] == {
        "CCSA": 2,
        "ICSA": 2,
        "PAYEMS": 2,
        "UNRATE": 2,
    }
    assert sorted(calls) == [
        ("CCSA", 52),
        ("ICSA", 52),
        ("PAYEMS", 24),
        ("UNRATE", 24),
    ]
    assert counts == {
        "continuing_claims": 2,
        "initial_jobless_claims": 2,
        "nonfarm_payrolls": 2,
        "unemployment_rate": 2,
    }
    assert rows_by_metric["unemployment_rate"][0]["source_series"] == "UNRATE"
    assert rows_by_metric["initial_jobless_claims"][0]["source_series"] == "ICSA"
    assert rows_by_metric["nonfarm_payrolls"][0]["source_series"] == "PAYEMS"
    assert rows_by_metric["continuing_claims"][0]["source_series"] == "CCSA"
    assert all(row["source"] == "FRED" for row in all_rows)
    assert all(row["provider"] == "FRED" for row in all_rows)
    assert all(row["source_badge"] == "official" for row in all_rows)
    assert all(row["freshness_status"] == "historical" for row in all_rows)
    assert all(row["metric_kind"] == "raw" for row in all_rows)
    assert "provider_payload" not in text
    assert "api_key" not in text
    assert "holding" not in text
