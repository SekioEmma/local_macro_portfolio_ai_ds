from datetime import date, timedelta

from data_quality import historical_percentile_metrics as percentile
from tests.helpers.market_history_fixtures import (
    insert_market_observations_many_for_tests,
    market_history_observation_for_tests,
    seed_market_history_series_for_tests,
)


def test_percentile_zscore_and_robust_zscore_with_5y_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2020, 1, 1), 1900)

    pct = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )
    z = percentile.build_metric_payload(
        _spec("high_yield_spread_zscore", "high_yield_spread", "zscore"),
        db_path=str(db_path),
    )
    robust = percentile.build_metric_payload(
        _spec("high_yield_spread_robust_zscore", "high_yield_spread", "robust_zscore"),
        db_path=str(db_path),
    )

    assert pct["lookback_window"] == "5Y rolling"
    assert pct["history_quality_status"] == "sufficient"
    assert pct["percentile_band"] == "extreme"
    assert z["zscore_band"] in {"elevated", "high"}
    assert robust["robust_zscore"] is not None
    assert robust["robust_zscore_band"] in {"elevated", "high"}
    assert robust["ai_context_allowed"] is True
    assert robust["trigger_eligibility"] == "hard_trigger_allowed"


def test_3y_fallback_is_limited_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2022, 1, 1), 1200)

    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(db_path))

    assert row["lookback_window"] == "3Y rolling limited_history"
    assert row["history_quality_status"] == "limited_history"
    assert row["ai_context_allowed"] is True


def test_less_than_3y_history_blocks_ai_context(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2024, 1, 1), 500)

    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(db_path))

    assert row["status"] == "insufficient_history"
    assert row["lookback_window"] == "all_available_limited"
    assert row["ai_context_allowed"] is False
    assert row["trigger_eligibility"] == "not_eligible"


def test_missing_input_blocks_ai_context(tmp_path):
    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(tmp_path / "missing.sqlite3"),
    )

    assert row["status"] == "missing"
    assert row["source_badge"] == "missing"
    assert row["ai_context_allowed"] is False


def test_stale_latest_input_blocks_ai_context(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2020, 1, 1), 100)
    _insert(db_path, "vix", "2026-03-01", 80.0, freshness_status="stale")

    row = percentile.build_metric_payload(_spec("vix_percentile", "vix"), db_path=str(db_path))

    assert row["status"] == "stale"
    assert row["ai_context_allowed"] is False
    assert row["missing_reason"] == "latest_input_unusable"


def test_lower_is_more_stress_band_for_drawdown_uses_damage_direction(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    start = date(2020, 1, 1)
    insert_market_observations_many_for_tests(
        db_path,
        [
            market_history_observation_for_tests(
                "sp500_drawdown_3m",
                (start + timedelta(days=index)).isoformat(),
                -1.0 * (index + 1),
            )
            for index in range(1900)
        ],
    )

    row = percentile.build_metric_payload(
        _spec(
            "sp500_drawdown_3m_percentile",
            "sp500_drawdown_3m",
            "percentile",
            direction="lower_is_more_stress",
        ),
        db_path=str(db_path),
    )

    assert row["status"] == "stress"
    assert row["percentile_band"] == "extreme"
    assert row["value"] < 10
    assert "lower values represent higher damage/severity" in row["interpretation_hint"]


def test_robust_zscore_zero_mad_is_not_available(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "dgs30", date(2020, 1, 1), 1900, constant=5.0)

    row = percentile.build_metric_payload(
        _spec("dgs30_robust_zscore", "dgs30", "robust_zscore"),
        db_path=str(db_path),
    )

    assert row["status"] == "not_available"
    assert row["ai_context_allowed"] is False
    assert row["missing_reason"] == "robust_zscore_not_available_zero_mad"


def test_proxy_source_becomes_proxy_auxiliary_only(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(
        db_path,
        "nasdaq100_drawdown_3m",
        date(2020, 1, 1),
        1900,
        source_badge="proxy",
        source="yfinance",
        source_series="QQQ",
    )

    row = percentile.build_metric_payload(
        _spec(
            "nasdaq100_drawdown_3m_robust_zscore",
            "nasdaq100_drawdown_3m",
            "robust_zscore",
            direction="lower_is_more_stress",
        ),
        db_path=str(db_path),
    )

    assert row["ai_context_allowed"] is True
    assert row["trigger_eligibility"] == "proxy_auxiliary_only"
    assert row["ai_context_tier"] == "auxiliary_context"


def test_interpretation_boundary_excludes_probability_and_trading_instruction(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "dfii10", date(2020, 1, 1), 1900, source_series="DFII10")

    row = percentile.build_metric_payload(
        _spec("dfii10_percentile", "dfii10"),
        db_path=str(db_path),
    )

    text = f"{row['interpretation_boundary']} {row['interpretation_hint']}".lower()
    assert "not event odds" in text
    assert "not probabilities" in text
    assert "reference review only" in text
    assert "recession probability" not in text


def _spec(metric_key, source_metric_key, kind="percentile", direction="higher_is_more_stress"):
    return percentile.PercentileMetricSpec(
        metric_key,
        source_metric_key,
        metric_key,
        kind,
        direction,
        60,
        kind,
    )


def _insert_series(
    db_path,
    metric_key,
    start_date,
    count,
    *,
    constant=None,
    source="FRED",
    source_badge="official",
    source_series=None,
):
    seed_market_history_series_for_tests(
        db_path,
        metric_key,
        start_date,
        count,
        constant=constant,
        source=source,
        source_badge=source_badge,
        source_series=source_series,
    )


def _insert(
    db_path,
    metric_key,
    observation_date,
    value,
    *,
    source="FRED",
    source_badge="official",
    source_series=None,
    status="ok",
    freshness_status="historical",
):
    insert_market_observations_many_for_tests(
        db_path,
        [
            market_history_observation_for_tests(
                metric_key,
                observation_date,
                value,
                source=source,
                source_badge=source_badge,
                source_series=source_series,
                status=status,
                freshness_status=freshness_status,
            )
        ],
    )
