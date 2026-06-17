import json
import socket
import sys

import pytest

import ingest_market_history_from_dashboard as ingest
from data_providers import market_history_store as store


def test_ingest_dry_run_does_not_create_db(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest.build_ingest_summary(
        reports_dir=tmp_path,
        db_path=db_path,
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert summary["candidate_count"] >= 2
    assert summary["inserted_count"] == 0
    assert not db_path.exists()


def test_ingest_write_uses_tmp_db_and_filters_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest.build_ingest_summary(
        reports_dir=tmp_path,
        db_path=db_path,
        dry_run=False,
    )
    rows = store.list_market_observations(db_path=db_path)

    assert summary["inserted_count"] >= 2
    assert db_path.exists()
    assert rows
    assert all(row["metric_key"] != "holdings_updated_at" for row in rows)
    assert all("RAW_FUND" not in json.dumps(row, ensure_ascii=False) for row in rows)
    assert set(store.count_observations_by_metric(db_path=db_path)) >= {"dgs10", "vix"}


def test_ingest_second_write_updates_existing_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    first = ingest.build_ingest_summary(reports_dir=tmp_path, db_path=db_path, dry_run=False)
    second = ingest.build_ingest_summary(reports_dir=tmp_path, db_path=db_path, dry_run=False)

    assert first["inserted_count"] >= 2
    assert second["updated_count"] >= 2
    assert sum(store.count_observations_by_metric(db_path=db_path).values()) == (
        first["inserted_count"] + second["inserted_count"]
    )


def test_observation_from_evidence_row_skips_portfolio_and_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    evidence = ingest.dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
    )

    skipped = {
        ingest.observation_from_evidence_row(row)[1]
        for row in evidence.rows
        if ingest.observation_from_evidence_row(row)[0] is None
    }

    assert "portfolio_local_row" in skipped
    assert "value_missing" in skipped or any(reason.startswith("status_") for reason in skipped)


def test_cli_dry_run_outputs_summary(monkeypatch, tmp_path, capsys):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"

    exit_code = ingest.main(
        [
            "--dry-run",
            "--reports-dir",
            str(tmp_path),
            "--db-path",
            str(db_path),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["dry_run"] is True
    assert not db_path.exists()


def _write_fake_reports(tmp_path):
    generated_at = "2026-01-01T00:00:00+00:00"

    def metric(value, source="FRED", source_badge="official", status="ok"):
        return {
            "value": value,
            "status": status,
            "source": source,
            "source_badge": source_badge,
            "observation_date": "2026-01-01",
            "freshness_status": "fresh",
        }

    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "dgs10": metric(4.52),
                "dgs30": metric(4.83),
                "vix": metric(18.2, source="CBOE"),
                "dfii10": metric(None, status="missing"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "holdings_updated_at": "2026-01-01",
                "weights_ex_cash": {
                    "sp500": 0.54,
                    "nasdaq100": 0.17,
                    "short_bond": 0.19,
                    "gold": 0.10,
                },
                "target_allocation": {
                    "sp500": 0.50,
                    "nasdaq100": 0.20,
                    "short_bond": 0.20,
                    "gold": 0.10,
                },
                "holdings": [{"ticker": "RAW_FUND", "amount": 999}],
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in market history ingest tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
