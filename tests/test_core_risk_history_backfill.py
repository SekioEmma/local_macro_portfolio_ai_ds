import json
from datetime import date, timedelta

import ingest_core_risk_history as ingest
from data_providers import market_history_store


def test_default_dry_run_does_not_fetch_or_write(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"

    def _raise_fetch(*args, **kwargs):
        raise AssertionError("fetch should not run without --live")

    summary = ingest.build_ingest_summary(
        db_path=db_path,
        dry_run=True,
        live=False,
        fred_fetcher=_raise_fetch,
        yfinance_downloader=_raise_fetch,
    )

    assert summary["dry_run"] is True
    assert summary["live"] is False
    assert summary["planned_official_series"]["dgs30"]["series_id"] == "DGS30"
    assert summary["planned_official_series"]["dfii10"]["series_id"] == "DFII10"
    assert summary["fetched_official_series"] == 0
    assert not db_path.exists()


def test_live_without_write_normalizes_without_db_write(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest.build_ingest_summary(
        db_path=db_path,
        dry_run=True,
        live=True,
        metric="dgs30",
        fred_fetcher=_fake_fred_fetcher,
    )

    assert summary["fetched_official_series"] == 1
    assert summary["normalized_raw_observations"] == 3
    assert summary["inserted_count"] == 0
    assert not db_path.exists()


def test_official_history_normalization_preserves_metadata(tmp_path):
    records = ingest.fetch_and_normalize_official(
        {
            "dgs30": {
                "metric_key": "dgs30",
                "provider": "FRED",
                "series_id": "DGS30",
                "source": "FRED",
                "source_badge": "official",
                "unit": "percent",
            }
        },
        limit=3,
        fetcher=_fake_fred_fetcher,
    )
    observation = records["observations"][0]

    assert observation["metric_key"] == "dgs30"
    assert observation["source"] == "FRED"
    assert observation["source_badge"] == "official"
    assert observation["source_series"] == "DGS30"
    assert observation["observation_date"] == "2026-01-03"


def test_yfinance_history_never_pretends_to_be_official(tmp_path):
    mappings = {
        "^GSPC": {
            "metric_key": "sp500",
            "symbol": "^GSPC",
            "source_badge": "unofficial_fallback",
            "metric_kind": "index",
            "unit": "index",
            "interpretation_hint": "fake",
        }
    }

    records = ingest.fetch_and_normalize_yfinance(
        mappings,
        period="1mo",
        downloader=_fake_yfinance_downloader,
    )

    assert {item["source_badge"] for item in records["observations"]} == {"unofficial_fallback"}
    assert all(item["source_badge"] != "official" for item in records["observations"])


def test_missing_source_mapping_is_reported(tmp_path):
    summary = ingest.build_ingest_summary(
        db_path=tmp_path / "market_history.sqlite3",
        dry_run=True,
        live=False,
        metric="unknown_core_metric",
    )

    assert "unknown_core_metric" in summary["missing_source_mappings"]


def test_live_write_materializes_derived_history_from_tmp_db(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for index in range(100):
        current = date(2025, 1, 1) + timedelta(days=index)
        _insert(db_path, "sp500", current.isoformat(), 100.0 + index)
        _insert(db_path, "initial_jobless_claims", current.isoformat(), 200000.0 + index)

    summary = ingest.build_ingest_summary(
        db_path=db_path,
        dry_run=False,
        live=True,
        metric="sp500_drawdown_3m",
    )
    rows = market_history_store.list_market_observations(
        metric_key="sp500_drawdown_3m",
        db_path=db_path,
        limit=200,
    )

    assert summary["derived_observations"] > 0
    assert rows
    assert {row["source_badge"] for row in rows} == {"derived"}
    assert all(row["metric_kind"] == "derived" for row in rows)


def test_claims_4w_average_uses_observation_count_not_daily_fill(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for index in range(4):
        current = date(2025, 1, 1) + timedelta(days=index * 7)
        _insert(db_path, "continuing_claims", current.isoformat(), 1000.0 + index)

    derived = ingest.build_derived_history_observations(
        metrics=["continuing_claims_4w_avg"],
        db_path=db_path,
    )

    assert len(derived) == 1
    assert derived[0]["metric_key"] == "continuing_claims_4w_avg"
    assert derived[0]["value"] == 1001.5
    assert "4 observation rolling average" in json.dumps(derived[0]["lineage"])


def test_cli_dry_run_does_not_write(tmp_path, capsys):
    db_path = tmp_path / "market_history.sqlite3"

    exit_code = ingest.main(["--dry-run", "--db-path", str(db_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["live"] is False
    assert not db_path.exists()


def _fake_fred_fetcher(series_id, limit):
    return {
        "series_id": series_id,
        "limit": limit,
        "data": [
            {"date": "2026-01-03", "value": 3.0},
            {"date": "2026-01-02", "value": 2.0},
            {"date": "2026-01-01", "value": 1.0},
        ],
        "source": "FRED",
        "timestamp": "2026-01-04T00:00:00+00:00",
        "status": "ok",
        "error": None,
    }


def _fake_yfinance_downloader(**kwargs):
    return {
        "^GSPC": [{"date": "2026-01-01", "Adj Close": 100.0}],
    }


def _insert(db_path, metric_key, observation_date, value):
    source_badge = "unofficial_fallback" if metric_key == "sp500" else "official"
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "status": "ok",
            "source": "test",
            "source_badge": source_badge,
            "provider": "test",
            "source_series": metric_key.upper(),
            "generated_at": "2026-01-01T00:00:00+00:00",
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": False,
            "metric_kind": "raw",
        },
        db_path=db_path,
    )
