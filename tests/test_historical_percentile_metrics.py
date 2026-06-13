import math

from data_quality import historical_percentile_metrics as percentile
from data_quality import market_history_store


def test_percentile_and_zscore_with_sufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day in range(1, 61):
        _insert(db_path, "high_yield_spread", f"2026-01-{day:02d}", float(day))

    pct = percentile.build_metric_payload(
        percentile.PercentileMetricSpec(
            "high_yield_spread_percentile",
            "high_yield_spread",
            "HY percentile",
            "percentile",
            "higher_is_more_stress",
            60,
            "percentile",
        ),
        db_path=str(db_path),
    )
    z = percentile.build_metric_payload(
        percentile.PercentileMetricSpec(
            "high_yield_spread_zscore",
            "high_yield_spread",
            "HY z",
            "zscore",
            "higher_is_more_stress",
            60,
            "zscore",
        ),
        db_path=str(db_path),
    )

    assert pct["status"] == "stress"
    assert pct["value"] > 95
    assert z["status"] == "stress"
    assert z["value"] > 1.0
    assert z["source_badge"] == "derived"
    assert z["ai_context_allowed"] is True


def test_insufficient_history_blocks_ai_context(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "vix", "2026-01-01", 20.0)

    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(db_path))

    assert row["status"] == "insufficient_history"
    assert row["ai_context_allowed"] is False
    assert row["missing_reason"] == "insufficient_history_for_percentile"
    assert row["component_contributions"]["observation_count"] == 1


def test_missing_input_blocks_ai_context(tmp_path):
    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(tmp_path / "missing.sqlite3"))

    assert row["status"] == "missing"
    assert row["source_badge"] == "missing"
    assert row["ai_context_allowed"] is False


def test_stale_latest_input_blocks_ai_context(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day in range(1, 60):
        _insert(db_path, "vix", f"2026-01-{day:02d}", float(day))
    _insert(db_path, "vix", "2026-03-01", 80.0, freshness_status="stale")

    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(db_path))

    assert row["status"] == "stale"
    assert row["ai_context_allowed"] is False
    assert row["missing_reason"] == "latest_input_stale"


def test_higher_is_more_stress_status_mapping(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day in range(1, 61):
        _insert(db_path, "vix", f"2026-01-{day:02d}", float(day))

    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(db_path))

    assert row["status"] == "stress"


def test_lower_is_more_stress_status_mapping_for_drawdown(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day in range(1, 61):
        _insert(db_path, "sp500_drawdown_3m", f"2026-01-{day:02d}", float(day) * -1.0)

    row = percentile.build_metric_payload(
        percentile.PercentileMetricSpec(
            "sp500_drawdown_3m_percentile",
            "sp500_drawdown_3m",
            "S&P drawdown percentile",
            "percentile",
            "lower_is_more_stress",
            60,
            "percentile",
        ),
        db_path=str(db_path),
    )

    assert row["status"] == "stress"
    assert row["value"] < 5


def test_output_preserves_metadata_and_boundary(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day in range(1, 61):
        _insert(db_path, "dfii10", f"2026-01-{day:02d}", float(day), source_series="DFII10")

    row = percentile.build_metric_payload(_spec("dfii10_percentile", "dfii10"), db_path=str(db_path))

    assert row["input_evidence"][0]["metric_key"] == "dfii10"
    assert row["input_evidence"][0]["source_series"] == "DFII10"
    assert row["component_contributions"]["lookback_window"] == "all_available"
    assert row["component_contributions"]["observation_count"] == 60
    assert row["component_contributions"]["percentile_direction"] == "higher_is_more_stress"
    assert "not crash probability" in row["interpretation_boundary"]
    assert "buy/sell" in row["interpretation_boundary"]


def test_constant_history_blocks_zscore(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day in range(1, 61):
        _insert(db_path, "dgs30", f"2026-01-{day:02d}", 5.0)

    row = percentile.build_metric_payload(
        percentile.PercentileMetricSpec(
            "dgs30_zscore",
            "dgs30",
            "DGS30 z",
            "zscore",
            "higher_is_more_stress",
            60,
            "zscore",
        ),
        db_path=str(db_path),
    )

    assert row["status"] == "insufficient_history"
    assert row["ai_context_allowed"] is False


def _spec(metric_key, source_metric_key):
    return percentile.PercentileMetricSpec(
        metric_key,
        source_metric_key,
        metric_key,
        "percentile",
        "higher_is_more_stress",
        60,
        "percentile",
    )


def _insert(
    db_path,
    metric_key,
    observation_date,
    value,
    *,
    source_series=None,
    status="ok",
    freshness_status="historical",
):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "status": status,
            "source": "FRED",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": source_series or metric_key.upper(),
            "generated_at": "2026-01-01T00:00:00+00:00",
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "freshness_status": freshness_status,
            "ai_context_allowed": status == "ok",
            "metric_kind": "raw",
        },
        db_path=db_path,
    )
