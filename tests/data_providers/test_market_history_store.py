import sqlite3

import pytest

from data_providers import market_history_store as store


def test_initialize_market_history_db_is_idempotent(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"

    store.initialize_market_history_db(db_path)
    store.initialize_market_history_db(db_path)

    with store.connect_market_history_db(db_path) as connection:
        assert store.get_market_history_schema_version(connection=connection) == store.CURRENT_SCHEMA_VERSION
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {"schema_migrations", "market_observations"}.issubset(tables)


def test_upsert_market_observation_inserts_and_updates(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    first = store.upsert_market_observation(_observation("dgs10", 4.5), db_path=db_path)
    second = store.upsert_market_observation(_observation("dgs10", 4.6), db_path=db_path)

    rows = store.list_market_observations(metric_key="dgs10", db_path=db_path)

    assert first["status"] == "inserted"
    assert second["status"] == "updated"
    assert len(rows) == 1
    assert rows[0]["value_numeric"] == 4.6
    assert store.count_observations_by_metric(db_path=db_path) == {"dgs10": 1}


def test_batch_upsert_uses_one_atomic_operation_and_reports_counts(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    first = store.upsert_market_observations(
        [
            _observation("dgs2", 4.1),
            _observation("dgs10", 4.5),
        ],
        db_path=db_path,
    )
    second = store.upsert_market_observations(
        [
            _observation("dgs2", 4.2),
            _observation("dgs30", 4.8),
        ],
        db_path=db_path,
    )

    assert first == {
        "observation_count": 2,
        "inserted_count": 2,
        "updated_count": 0,
    }
    assert second == {
        "observation_count": 2,
        "inserted_count": 1,
        "updated_count": 1,
    }
    assert store.count_observations_by_metric(db_path=db_path) == {
        "dgs10": 1,
        "dgs2": 1,
        "dgs30": 1,
    }


def test_batch_upsert_validates_all_rows_before_writing(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observations(
            [
                _observation("dgs10", 4.5),
                _observation("bad", None),
            ],
            db_path=db_path,
        )

    assert not db_path.exists()


def test_same_date_prefers_official_source_over_later_fallback_write(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    store.upsert_market_observation(
        _observation("headline_cpi_yoy", 3.0, source="BLS"),
        db_path=db_path,
    )
    store.upsert_market_observation(
        _observation(
            "headline_cpi_yoy",
            2.9,
            source="FRED",
            source_badge="official_fallback",
        ),
        db_path=db_path,
    )

    latest = store.get_latest_observation("headline_cpi_yoy", db_path=db_path)
    rows = store.list_market_observations(
        metric_key="headline_cpi_yoy", db_path=db_path
    )

    assert latest["provider"] == "BLS"
    assert latest["source_badge"] == "official"
    assert [row["source_badge"] for row in rows] == [
        "official",
        "official_fallback",
    ]


def test_list_latest_and_counts_by_metric(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    store.upsert_market_observation(
        _observation("dgs10", 4.5, observation_date="2026-01-01"),
        db_path=db_path,
    )
    store.upsert_market_observation(
        _observation("dgs10", 4.7, observation_date="2026-01-03"),
        db_path=db_path,
    )
    store.upsert_market_observation(
        _observation("vix", 18.2, observation_date="2026-01-02", source="CBOE"),
        db_path=db_path,
    )

    latest = store.get_latest_observation("dgs10", db_path=db_path)

    assert latest["observation_date"] == "2026-01-03"
    assert [row["metric_key"] for row in store.list_market_observations(metric_key="dgs10", db_path=db_path)] == [
        "dgs10",
        "dgs10",
    ]
    assert store.count_observations_by_metric(db_path=db_path) == {"dgs10": 2, "vix": 1}


@pytest.mark.parametrize("source_badge", ["missing", "research_needed", "search-derived"])
def test_blocked_source_badges_are_rejected(tmp_path, source_badge):
    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observation(
            _observation("dgs10", 4.5, source_badge=source_badge),
            db_path=tmp_path / "market_history.sqlite3",
        )


@pytest.mark.parametrize(
    "status",
    ["missing", "research_needed", "not_available", "insufficient_history", "stale"],
)
def test_blocked_statuses_are_rejected(tmp_path, status):
    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observation(
            _observation("dgs10", 4.5, status=status),
            db_path=tmp_path / "market_history.sqlite3",
        )


def test_null_value_is_rejected(tmp_path):
    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observation(
            _observation("dgs10", None),
            db_path=tmp_path / "market_history.sqlite3",
        )


def test_portfolio_and_holdings_like_rows_are_rejected(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"

    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observation(_observation("holdings_updated_at", "2026-01-01"), db_path=db_path)
    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observation(
            {
                **_observation("dgs10", 4.5),
                "lineage": {"holdings": [{"ticker": "RAW_FUND"}]},
            },
            db_path=db_path,
        )


def test_raw_provider_secret_and_prompt_payloads_are_rejected(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    fake_secret = "sk-" + ("a" * 26)

    for payload in (
        {"raw_provider_response": {"value": 4.5}},
        {"raw_prompt": "do not store"},
        {"api_key": fake_secret},
    ):
        with pytest.raises(store.MarketHistoryValidationError):
            store.upsert_market_observation(
                {
                    **_observation("dgs10", 4.5),
                    "lineage": payload,
                },
                db_path=db_path,
            )


def test_derived_requires_lineage(tmp_path):
    with pytest.raises(store.MarketHistoryValidationError):
        store.upsert_market_observation(
            {
                **_observation("dgs10_5d_avg", 4.5),
                "source_badge": "derived",
                "metric_kind": "derived",
                "lineage": {},
            },
            db_path=tmp_path / "market_history.sqlite3",
        )


def test_summary_for_missing_db_is_empty(tmp_path):
    summary = store.get_market_history_summary(db_path=tmp_path / "missing.sqlite3")

    assert summary["market_history_db_exists"] is False
    assert summary["market_history_schema_version"] == 0
    assert summary["market_history_observation_count"] == 0


def _observation(
    metric_key,
    value,
    *,
    observation_date="2026-01-01",
    source="FRED",
    source_badge="official",
    status="ok",
    metric_kind="raw",
    lineage=None,
):
    return {
        "metric_key": metric_key,
        "observation_date": observation_date,
        "value": value,
        "value_text": str(value) if value is not None else None,
        "unit": "percent",
        "status": status,
        "source": source,
        "source_badge": source_badge,
        "provider": source,
        "source_series": metric_key.upper(),
        "generated_at": "2026-01-01T00:00:00+00:00",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "ai_context_allowed": True,
        "metric_kind": metric_kind,
        "lineage": lineage or {"source": "test"} if metric_kind == "derived" else lineage or {},
    }
