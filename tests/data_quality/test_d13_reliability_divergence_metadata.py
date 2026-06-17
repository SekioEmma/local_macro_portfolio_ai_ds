import json
from datetime import date, timedelta
from pathlib import Path

from data_quality import historical_percentile_metrics as percentile
from tests.helpers.market_history_fixtures import (
    insert_market_observations_many_for_tests,
    market_history_observation_for_tests,
    seed_market_history_series_for_tests,
)


METADATA_KEYS = (
    "reliability_band",
    "reliability_drivers",
    "divergence_band",
    "divergence_notes",
    "method_agreement",
    "normalization_methods_available",
    "percentile_zscore_alignment",
    "percentile_robust_zscore_alignment",
    "zscore_robust_zscore_alignment",
    "source_quality_note",
    "history_window_note",
)


# ---------------------------------------------------------------------------
# 9.1 Field presence
# ---------------------------------------------------------------------------


def test_reliability_metadata_fields_present_on_eligible_row(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2020, 1, 1), 1900)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )

    for key in METADATA_KEYS:
        assert key in row, f"top-level missing {key}"
        assert key in row["component_contributions"], f"component missing {key}"
    assert row["normalization_methods_available"] == {
        "percentile": True,
        "zscore": True,
        "robust_zscore": True,
    }


def test_reliability_metadata_fields_present_on_blocked_row(tmp_path):
    db_path = tmp_path / "missing.sqlite3"

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )

    assert row["status"] == "missing"
    for key in METADATA_KEYS:
        assert key in row
        assert key in row["component_contributions"]
    assert row["reliability_band"] == "insufficient"
    assert row["divergence_band"] == "not_available"
    assert row["method_agreement"] == "insufficient_methods"


def test_sanitized_d13_context_carries_reliability_metadata(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2020, 1, 1), 1900)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )
    row["module"] = "historical_risk_percentile"

    sanitized = percentile.sanitized_d13_context(row)
    for key in METADATA_KEYS:
        assert key in sanitized


# ---------------------------------------------------------------------------
# 9.2 Sufficient official aligned case
# ---------------------------------------------------------------------------


def test_sufficient_official_aligned_case_is_high_reliability(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    start = date(2020, 1, 1)
    # 1899 linearly increasing values (1..1899) then the latest sits at the
    # series median, so all three normalizations land in the "normal" band.
    rows = [
        market_history_observation_for_tests(
            "high_yield_spread",
            (start + timedelta(days=index)).isoformat(),
            float(index + 1),
        )
        for index in range(1899)
    ]
    rows.append(
        market_history_observation_for_tests(
            "high_yield_spread",
            (start + timedelta(days=1899)).isoformat(),
            950.0,
        )
    )
    insert_market_observations_many_for_tests(db_path, rows)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )

    assert row["history_quality_status"] == "sufficient"
    assert row["percentile_band"] == "normal"
    assert row["zscore_band"] == "normal"
    assert row["robust_zscore_band"] == "normal"
    assert row["divergence_band"] == "none"
    assert row["method_agreement"] == "all_available_aligned"
    assert row["reliability_band"] == "high"
    assert row["ai_context_allowed"] is True
    assert row["trigger_eligibility"] == "hard_trigger_allowed"
    assert "official_source" in row["reliability_drivers"]
    assert "sufficient_5y_history" in row["reliability_drivers"]
    assert row["percentile_zscore_alignment"] == "aligned"
    assert row["percentile_robust_zscore_alignment"] == "aligned"
    assert row["zscore_robust_zscore_alignment"] == "aligned"


# ---------------------------------------------------------------------------
# 9.3 Limited 3Y case
# ---------------------------------------------------------------------------


def test_limited_3y_history_is_medium_reliability(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2022, 1, 1), 1200)

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )

    assert row["lookback_window"] == "3Y rolling limited_history"
    assert row["history_quality_status"] == "limited_history"
    assert row["reliability_band"] in {"medium", "low"}
    assert row["reliability_band"] != "high"
    assert "limited_3y_history" in row["reliability_drivers"]
    assert row["trigger_eligibility"] == "hard_trigger_allowed"
    assert "limited" in row["interpretation_hint"] or "limited" in row["history_window_note"]


# ---------------------------------------------------------------------------
# 9.4 Insufficient history case
# ---------------------------------------------------------------------------


def test_insufficient_history_is_insufficient_reliability(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2024, 1, 1), 500)

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )

    assert row["status"] == "insufficient_history"
    assert row["reliability_band"] == "insufficient"
    assert row["divergence_band"] == "not_available"
    assert row["ai_context_allowed"] is False
    assert row["trigger_eligibility"] == "not_eligible"
    assert "insufficient_history" in row["reliability_drivers"]


# ---------------------------------------------------------------------------
# 9.5 Divergence case
# ---------------------------------------------------------------------------


def _insert_divergence_series(db_path):
    """Heavy-tailed series: 1600 values uniform on (0, 10], 299 outliers
    uniform on (50, 100], and a latest value of 10.0. Percentile sees the
    latest at the top of the dense cluster (~high band) while z-score and
    robust z-score, anchored on the full distribution, see it as ~normal."""
    start = date(2020, 1, 1)
    rows = [
        market_history_observation_for_tests(
            "high_yield_spread",
            (start + timedelta(days=index)).isoformat(),
            (index + 1) * 10.0 / 1600,
        )
        for index in range(1600)
    ]
    rows.extend(
        market_history_observation_for_tests(
            "high_yield_spread",
            (start + timedelta(days=1600 + index)).isoformat(),
            50.0 + (index + 1) * 50.0 / 300,
        )
        for index in range(299)
    )
    rows.append(
        market_history_observation_for_tests(
            "high_yield_spread",
            (start + timedelta(days=1899)).isoformat(),
            10.0,
        )
    )
    insert_market_observations_many_for_tests(db_path, rows)


def test_divergence_case_marks_divergence_without_promoting_trigger(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_divergence_series(db_path)

    pct_row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )
    robust_row = percentile.build_metric_payload(
        _spec("high_yield_spread_robust_zscore", "high_yield_spread", "robust_zscore"),
        db_path=str(db_path),
    )

    # Original numeric values are preserved (no formula change).
    assert pct_row["percentile"] is not None
    assert robust_row["robust_zscore"] is not None

    # Methods disagree on the broad level of the latest observation.
    assert pct_row["divergence_band"] in {"mild", "material"}
    assert pct_row["method_agreement"] in {
        "mostly_aligned",
        "mixed",
        "divergent",
    }
    assert pct_row["reliability_band"] != "high"
    assert "method_divergence" in pct_row["reliability_drivers"]

    # Boundary: divergence notes never reach for probability / trading words.
    notes = pct_row["divergence_notes"].lower()
    for forbidden in (
        "probability",
        "forecast",
        "buy ",
        "sell ",
        "hedge",
        "rebalance",
        "target allocation",
        "expected return",
    ):
        assert forbidden not in notes


def test_divergence_does_not_silently_revoke_ai_context_eligibility(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_divergence_series(db_path)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )

    # AI context eligibility comes from the existing rule set; divergence is
    # explanatory metadata only.
    assert row["ai_context_allowed"] is True


# ---------------------------------------------------------------------------
# 9.6 Zero std / zero MAD case
# ---------------------------------------------------------------------------


def test_zero_mad_robust_zscore_is_not_available_and_reliability_is_insufficient(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "dgs30", date(2020, 1, 1), 1900, constant=5.0)

    row = percentile.build_metric_payload(
        _spec("dgs30_robust_zscore", "dgs30", "robust_zscore"),
        db_path=str(db_path),
    )

    assert row["status"] == "not_available"
    assert row["reliability_band"] == "insufficient"
    assert row["divergence_band"] == "not_available"
    assert row["missing_reason"] == "robust_zscore_not_available_zero_mad"
    assert "robust_zscore_unavailable_zero_mad" in row["reliability_drivers"]


def test_zero_std_zscore_is_not_available_and_reliability_is_insufficient(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "dgs30", date(2020, 1, 1), 1900, constant=5.0)

    row = percentile.build_metric_payload(
        _spec("dgs30_zscore", "dgs30", "zscore"),
        db_path=str(db_path),
    )

    assert row["status"] == "not_available"
    assert row["reliability_band"] == "insufficient"
    assert row["missing_reason"] == "zscore_not_available_zero_std"
    assert "zscore_unavailable_zero_std" in row["reliability_drivers"]


# ---------------------------------------------------------------------------
# 9.7 Direction handling
# ---------------------------------------------------------------------------


def test_drawdown_direction_is_preserved_after_reliability_metadata(tmp_path):
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

    # Existing direction behavior intact; reliability metadata uses the same
    # already-direction-aware band, so we do not double-flip the direction.
    assert row["percentile_direction"] == "lower_is_more_stress"
    assert row["percentile_band"] == "extreme"
    assert row["status"] == "stress"
    assert row["divergence_band"] in {"none", "mild", "material"}
    assert row["method_agreement"] in {
        "all_available_aligned",
        "mostly_aligned",
        "mixed",
        "divergent",
    }


# ---------------------------------------------------------------------------
# 9.8 Source quality
# ---------------------------------------------------------------------------


def test_proxy_source_keeps_proxy_auxiliary_and_marks_low_reliability(tmp_path):
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

    assert row["trigger_eligibility"] == "proxy_auxiliary_only"
    assert row["ai_context_tier"] == "auxiliary_context"
    assert row["reliability_band"] == "low"
    assert "proxy_source_auxiliary_only" in row["reliability_drivers"]
    assert "proxy" in row["source_quality_note"]


def test_unofficial_fallback_source_is_at_most_medium_reliability(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(
        db_path,
        "vix",
        date(2020, 1, 1),
        1900,
        source_badge="unofficial_fallback",
    )

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )

    assert row["reliability_band"] in {"medium", "low"}
    assert row["reliability_band"] != "high"
    assert "unofficial_fallback_source" in row["reliability_drivers"]
    assert row["trigger_eligibility"] == "auxiliary_only"


# ---------------------------------------------------------------------------
# 9.9 AI context / golden contract
# ---------------------------------------------------------------------------


def test_insufficient_d13_row_is_excluded_from_ai_factual_context(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2024, 1, 1), 500)

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )

    assert row["ai_context_allowed"] is False
    assert row["reliability_band"] == "insufficient"
    assert row["ai_context_tier"] == "excluded"


def test_reliability_metadata_does_not_relax_ai_context_eligibility(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2024, 1, 1), 500)

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )

    # Even though reliability metadata is informative, ai_context_allowed
    # remains False; metadata cannot re-enable a blocked row.
    assert row["ai_context_allowed"] is False


def test_reliability_metadata_does_not_inject_forbidden_language(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "dfii10", date(2020, 1, 1), 1900, source_series="DFII10")

    row = percentile.build_metric_payload(
        _spec("dfii10_percentile", "dfii10"),
        db_path=str(db_path),
    )
    serialized = json.dumps(row, sort_keys=True).lower()

    for phrase in (
        "crash probability",
        "recession probability",
        "market direction probability",
        "expected return",
        "predicted return",
        "future return",
        "trade signal",
        "target allocation",
        "buy",
        "sell",
        "hedge",
        "rebalance",
    ):
        assert phrase not in serialized


# ---------------------------------------------------------------------------
# 9.10 No forbidden surfaces in changed file
# ---------------------------------------------------------------------------


def test_d13_production_file_has_no_forbidden_surfaces():
    text = Path("src/data_quality/historical_percentile_metrics.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/external",
        "DeepSeek",
        "Tavily",
        "external_llm.yaml",
        ".env",
        "crash_probability",
        "recession_probability",
        "market_direction_probability",
        "expected_return",
        "predicted_return",
        "future_return",
        "trade_signal",
        "target_allocation",
    ):
        assert token not in text


# ---------------------------------------------------------------------------
# Helpers (mirroring tests/test_historical_percentile_metrics.py)
# ---------------------------------------------------------------------------


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
