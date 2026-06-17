import json
import socket

import ingest_yfinance_history as ingest
from data_providers import market_history_store


def test_default_dry_run_without_live_does_not_call_downloader_or_write(tmp_path):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    def _raise_if_called(**kwargs):
        raise AssertionError("downloader should not be called without --live")

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        dry_run=True,
        live=False,
        downloader=_raise_if_called,
    )

    assert summary["dry_run"] is True
    assert summary["live"] is False
    assert summary["enabled_symbols"] == 2
    assert summary["fetched_symbols"] == 0
    assert summary["skipped_reasons"] == {"live_disabled": 2}
    assert not db_path.exists()


def test_live_dry_run_with_fake_downloader_normalizes_without_writing(tmp_path):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        dry_run=True,
        live=True,
        downloader=_fake_downloader,
    )

    assert summary["normalized_observations"] == 2
    assert summary["source_badge_distribution"] == {"proxy": 1, "unofficial_fallback": 1}
    assert summary["inserted_count"] == 0
    assert not db_path.exists()


def test_live_write_with_fake_downloader_uses_tmp_db(tmp_path):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        dry_run=False,
        live=True,
        downloader=_fake_downloader,
    )
    observations = market_history_store.list_market_observations(db_path=db_path)

    assert summary["inserted_count"] == 2
    assert db_path.exists()
    assert {item["provider"] for item in observations} == {"yfinance"}
    assert {item["source_badge"] for item in observations} == {"unofficial_fallback", "proxy"}
    assert all(item["ai_context_allowed"] is False for item in observations)
    assert "RAW_FUND" not in json.dumps(observations, ensure_ascii=False)


def test_second_write_updates_existing_rows(tmp_path):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    first = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        dry_run=False,
        live=True,
        downloader=_fake_downloader,
    )
    second = ingest.build_ingest_summary(
        config_path=config_path,
        db_path=db_path,
        dry_run=False,
        live=True,
        downloader=_fake_downloader,
    )

    assert first["inserted_count"] == 2
    assert second["updated_count"] == 2
    assert sum(market_history_store.count_observations_by_metric(db_path=db_path).values()) == 2


def test_cli_dry_run_does_not_write(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    exit_code = ingest.main(["--dry-run", "--config", str(config_path), "--db-path", str(db_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["live"] is False
    assert not db_path.exists()


def test_no_network_access(monkeypatch, tmp_path):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in yfinance ingest tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)

    summary = ingest.build_ingest_summary(
        config_path=_write_config(tmp_path),
        db_path=tmp_path / "market_history.sqlite3",
        dry_run=True,
        live=False,
    )

    assert summary["skipped_reasons"]["live_disabled"] == 2


def _fake_downloader(**kwargs):
    return {
        "^GSPC": [{"date": "2026-01-01", "Adj Close": 100.0}],
        "SPY": [{"date": "2026-01-01", "Close": 200.0}],
    }


def _write_config(tmp_path):
    path = tmp_path / "yfinance_history.yaml"
    path.write_text(
        """
yfinance_history:
  index_unofficial_fallback:
    - metric_key: sp500
      symbol: "^GSPC"
      display_name: "S&P 500 Index"
      source_badge: unofficial_fallback
      metric_kind: index
      unit: index
      enabled: true
      interpretation_hint: "fake index fallback"
  etf_proxy:
    - metric_key: spy_proxy
      symbol: SPY
      display_name: "SPY proxy"
      source_badge: proxy
      metric_kind: proxy
      unit: price
      enabled: true
      interpretation_hint: "fake ETF proxy"
""",
        encoding="utf-8",
    )
    return path
