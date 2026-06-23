from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from data_quality import historical_percentile_metadata as metadata
from data_quality import historical_percentile_metrics as percentile
from tests.helpers.market_history_fixtures import seed_market_history_series_for_tests


def test_reliability_metadata_exact_output_for_representative_cases():
    assert metadata.build_reliability_metadata(
        status="ok",
        history_quality_status="sufficient",
        latest_source_badge="official",
        trigger_eligibility="hard_trigger_allowed",
        percentile_band="normal",
        zscore_band="normal",
        robust_zscore_band="normal",
        lookback_window="5Y rolling",
        observation_count=1900,
        minimum_observation_count=60,
        blocked=False,
    ) == {
        "reliability_band": "high",
        "reliability_drivers": [
            "method_agreement",
            "official_source",
            "percentile_available",
            "robust_zscore_available",
            "sufficient_5y_history",
            "zscore_available",
        ],
        "divergence_band": "none",
        "divergence_notes": (
            "percentile, z-score, and robust z-score bands align on the same broad level"
        ),
        "method_agreement": "all_available_aligned",
        "normalization_methods_available": {
            "percentile": True,
            "zscore": True,
            "robust_zscore": True,
        },
        "percentile_zscore_alignment": "aligned",
        "percentile_robust_zscore_alignment": "aligned",
        "zscore_robust_zscore_alignment": "aligned",
        "source_quality_note": (
            "latest input source_badge=official; "
            "trigger_eligibility=hard_trigger_allowed"
        ),
        "history_window_note": (
            "lookback_window=5Y rolling; "
            "history_quality_status=sufficient; observation_count=1900/60"
        ),
    }

    limited = metadata.build_reliability_metadata(
        status="ok",
        history_quality_status="limited_history",
        latest_source_badge="official",
        trigger_eligibility="hard_trigger_allowed",
        percentile_band="normal",
        zscore_band="normal",
        robust_zscore_band="normal",
        lookback_window="3Y rolling limited_history",
        observation_count=1200,
        minimum_observation_count=60,
        blocked=False,
    )
    assert limited["reliability_band"] == "medium"
    assert limited["divergence_band"] == "none"
    assert limited["method_agreement"] == "all_available_aligned"
    assert limited["reliability_drivers"] == [
        "limited_3y_history",
        "method_agreement",
        "official_source",
        "percentile_available",
        "robust_zscore_available",
        "zscore_available",
    ]

    proxy = metadata.build_reliability_metadata(
        status="ok",
        history_quality_status="sufficient",
        latest_source_badge="proxy",
        trigger_eligibility="proxy_auxiliary_only",
        percentile_band="normal",
        zscore_band="normal",
        robust_zscore_band="normal",
        lookback_window="5Y rolling",
        observation_count=1900,
        minimum_observation_count=60,
        blocked=False,
    )
    assert proxy["reliability_band"] == "low"
    assert "proxy_source_auxiliary_only" in proxy["reliability_drivers"]

    material = metadata.build_reliability_metadata(
        status="ok",
        history_quality_status="sufficient",
        latest_source_badge="official",
        trigger_eligibility="hard_trigger_allowed",
        percentile_band="high",
        zscore_band="normal",
        robust_zscore_band="normal",
        lookback_window="5Y rolling",
        observation_count=1900,
        minimum_observation_count=60,
        blocked=False,
    )
    assert material["reliability_band"] == "low"
    assert material["divergence_band"] == "material"
    assert material["method_agreement"] == "mixed"
    assert material["percentile_zscore_alignment"] == "materially_divergent"
    assert material["percentile_robust_zscore_alignment"] == "materially_divergent"
    assert material["zscore_robust_zscore_alignment"] == "aligned"
    assert "method_divergence" in material["reliability_drivers"]

    blocked = metadata.build_reliability_metadata(
        status="insufficient_history",
        history_quality_status="insufficient_history",
        latest_source_badge="official",
        trigger_eligibility="not_eligible",
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
        lookback_window="all_available_limited",
        observation_count=500,
        minimum_observation_count=60,
        blocked=True,
        missing_reason="insufficient_history_for_percentile",
    )
    assert blocked["reliability_band"] == "insufficient"
    assert blocked["divergence_band"] == "not_available"
    assert blocked["method_agreement"] == "insufficient_methods"
    assert blocked["reliability_drivers"] == [
        "insufficient_history",
        "insufficient_history_blocked",
        "official_source",
        "percentile_band_unavailable",
        "robust_zscore_band_unavailable",
        "zscore_band_unavailable",
    ]

    zero_std = metadata.build_reliability_metadata(
        status="not_available",
        history_quality_status="sufficient",
        latest_source_badge="official",
        trigger_eligibility="not_eligible",
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
        lookback_window="5Y rolling",
        observation_count=1900,
        minimum_observation_count=60,
        blocked=True,
        missing_reason="zscore_not_available_zero_std",
    )
    assert zero_std["reliability_band"] == "insufficient"
    assert zero_std["divergence_band"] == "not_available"
    assert "zscore_unavailable_zero_std" in zero_std["reliability_drivers"]

    zero_mad = metadata.build_reliability_metadata(
        status="not_available",
        history_quality_status="sufficient",
        latest_source_badge="official",
        trigger_eligibility="not_eligible",
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
        lookback_window="5Y rolling",
        observation_count=1900,
        minimum_observation_count=60,
        blocked=True,
        missing_reason="robust_zscore_not_available_zero_mad",
    )
    assert "robust_zscore_unavailable_zero_mad" in zero_mad["reliability_drivers"]


def test_credit_oas_coverage_exact_output_for_gate_and_reference_cases():
    latest = _latest("high_yield_spread", value=1095.0, source_series="BAMLH0A0HYM2")
    below_gate = metadata.build_credit_oas_coverage_metadata(
        _spec("high_yield_spread"),
        status="insufficient_history",
        history_quality_status="insufficient_history",
        observation_count=1095,
        latest=latest,
        lookback=_lookback(date(2023, 6, 13), 1095, "all_available_limited"),
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
    )
    assert below_gate == {
        "history_coverage_status": "below_exact_gate",
        "provider_rebuild_status": "provider_rebuild_limited",
        "normalization_availability": {
            "percentile_available": False,
            "zscore_available": False,
            "robust_zscore_available": False,
            "current_level_available": True,
            "long_history_reference_available": False,
        },
        "coverage_diagnostics": {
            "local_start": "2023-06-13",
            "local_end": "2026-06-11",
            "observation_count": 1095,
            "distinct_dates": 1095,
            "coverage_days": 1094,
            "required_days": 1095,
            "days_short": 1,
            "provider_start_now": None,
            "provider_end_now": None,
        },
        "credit_reference_role": "primary_oas_series",
        "substitution_policy": "no_substitution",
        "long_history_reference_status": "unavailable_for_primary_series",
    }

    investment_grade = metadata.build_credit_oas_coverage_metadata(
        _spec("investment_grade_spread"),
        status="insufficient_history",
        history_quality_status="insufficient_history",
        observation_count=1095,
        latest=_latest(
            "investment_grade_spread", value=1095.0, source_series="BAMLC0A0CM"
        ),
        lookback=_lookback(date(2023, 6, 13), 1095, "all_available_limited"),
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
    )
    assert investment_grade["history_coverage_status"] == "below_exact_gate"
    assert investment_grade["coverage_diagnostics"]["days_short"] == 1
    assert investment_grade["credit_reference_role"] == "primary_oas_series"

    exact_gate = metadata.build_credit_oas_coverage_metadata(
        _spec("high_yield_spread"),
        status="ok",
        history_quality_status="limited_history",
        observation_count=1096,
        latest=latest,
        lookback=_lookback(date(2023, 6, 13), 1096, "3Y rolling limited_history"),
        percentile_band="normal",
        zscore_band="normal",
        robust_zscore_band="normal",
    )
    assert exact_gate["history_coverage_status"] == "limited_history"
    assert exact_gate["coverage_diagnostics"]["coverage_days"] == 1095
    assert exact_gate["coverage_diagnostics"]["days_short"] == 0

    baa10y = metadata.build_credit_oas_coverage_metadata(
        _spec("BAA10Y"),
        status="ok",
        history_quality_status="sufficient",
        observation_count=2000,
        latest=_latest("BAA10Y", value=2.5, source_series="BAA10Y"),
        lookback=_lookback(date(2020, 1, 1), 2000, "5Y rolling"),
        percentile_band="normal",
        zscore_band="normal",
        robust_zscore_band="normal",
    )
    assert baa10y["credit_reference_role"] == "long_history_credit_proxy_reference"
    assert baa10y["provider_rebuild_status"] == "reproducible_long_history"
    assert baa10y["substitution_policy"] == "proxy_reference_not_oas_substitute"
    assert baa10y["long_history_reference_status"] == "available_proxy_reference"
    assert baa10y["normalization_availability"]["long_history_reference_available"] is True

    non_credit = metadata.build_credit_oas_coverage_metadata(
        _spec("vix"),
        status="ok",
        history_quality_status="sufficient",
        observation_count=1900,
        latest=_latest("vix", value=20.0, source_series="VIXCLS"),
        lookback=_lookback(date(2020, 1, 1), 1900, "5Y rolling"),
        percentile_band="normal",
        zscore_band="normal",
        robust_zscore_band="normal",
    )
    assert non_credit["credit_reference_role"] == "non_credit_percentile_metric"
    assert non_credit["provider_rebuild_status"] == "not_applicable"
    assert non_credit["substitution_policy"] == "not_applicable"
    assert non_credit["long_history_reference_status"] == "not_applicable"


def test_current_level_availability_gate():
    assert metadata._current_level_available(_latest("vix", value=1.0)) is True
    assert metadata._current_level_available(_latest("vix", value=None)) is False
    assert (
        metadata._current_level_available(_latest("vix", value_numeric=1.0, value=None))
        is True
    )
    assert metadata._current_level_available(_latest("vix", value=1.0, status="missing")) is False
    assert (
        metadata._current_level_available(_latest("vix", value=1.0, source_badge="missing"))
        is False
    )
    for freshness_status in ("stale", "unknown", "missing"):
        assert (
            metadata._current_level_available(
                _latest("vix", value=1.0, freshness_status=freshness_status)
            )
            is False
        )


def test_historical_percentile_metrics_compatibility_aliases_and_constants_align():
    assert percentile.PRIMARY_CREDIT_OAS_METRICS == metadata.PRIMARY_CREDIT_OAS_METRICS
    assert (
        percentile.LONG_HISTORY_CREDIT_PROXY_REFERENCES
        == metadata.LONG_HISTORY_CREDIT_PROXY_REFERENCES
    )
    assert (
        percentile.CREDIT_OAS_PROVIDER_REBUILD_STATUS
        == metadata.CREDIT_OAS_PROVIDER_REBUILD_STATUS
    )
    assert percentile.BROAD_BAND_LEVELS == metadata.BROAD_BAND_LEVELS
    assert percentile.FALLBACK_WINDOW_DAYS == metadata.FALLBACK_WINDOW_DAYS
    assert percentile.SUFFICIENT_HISTORY_STATUS == metadata.SUFFICIENT_HISTORY_STATUS
    assert percentile.LIMITED_HISTORY_STATUS == metadata.LIMITED_HISTORY_STATUS
    assert percentile.INSUFFICIENT_HISTORY_STATUS == metadata.INSUFFICIENT_HISTORY_STATUS
    assert percentile.BAD_FRESHNESS == metadata.BAD_FRESHNESS
    assert percentile.BAD_STATUSES == metadata.BAD_STATUSES
    assert percentile.OFFICIAL_BADGES == metadata.OFFICIAL_BADGES
    assert percentile._reliability_metadata is metadata.build_reliability_metadata
    assert (
        percentile._credit_oas_coverage_metadata
        is metadata.build_credit_oas_coverage_metadata
    )


def test_build_metric_payload_representative_outputs_remain_stable(tmp_path):
    official_db = tmp_path / "official.sqlite3"
    seed_market_history_series_for_tests(
        official_db,
        "vix",
        date(2020, 1, 1),
        1900,
        source_series="VIXCLS",
    )
    official = percentile.build_metric_payload(
        _payload_spec("vix_percentile", "vix"),
        db_path=str(official_db),
    )
    assert official["lookback_window"] == "5Y rolling"
    assert official["history_quality_status"] == "sufficient"
    assert official["normalization_methods_available"] == {
        "percentile": True,
        "zscore": True,
        "robust_zscore": True,
    }
    assert official["history_coverage_status"] == "sufficient_history"
    assert official["ai_context_allowed"] is True

    limited_db = tmp_path / "limited.sqlite3"
    seed_market_history_series_for_tests(limited_db, "vix", date(2022, 1, 1), 1200)
    limited = percentile.build_metric_payload(
        _payload_spec("vix_percentile", "vix"),
        db_path=str(limited_db),
    )
    assert limited["lookback_window"] == "3Y rolling limited_history"
    assert limited["history_quality_status"] == "limited_history"
    assert limited["history_coverage_status"] == "limited_history"

    below_gate_db = tmp_path / "below_gate.sqlite3"
    seed_market_history_series_for_tests(
        below_gate_db,
        "high_yield_spread",
        date(2023, 6, 13),
        1095,
        source_series="BAMLH0A0HYM2",
    )
    below_gate = percentile.build_metric_payload(
        _payload_spec("high_yield_spread_percentile", "high_yield_spread"),
        db_path=str(below_gate_db),
    )
    assert below_gate["status"] == "insufficient_history"
    assert below_gate["history_coverage_status"] == "below_exact_gate"
    assert below_gate["coverage_diagnostics"]["coverage_days"] == 1094
    assert below_gate["coverage_diagnostics"]["days_short"] == 1

    constant_db = tmp_path / "constant.sqlite3"
    seed_market_history_series_for_tests(
        constant_db,
        "dgs30",
        date(2020, 1, 1),
        1900,
        constant=5.0,
    )
    zero_std = percentile.build_metric_payload(
        _payload_spec("dgs30_zscore", "dgs30", "zscore"),
        db_path=str(constant_db),
    )
    zero_mad = percentile.build_metric_payload(
        _payload_spec("dgs30_robust_zscore", "dgs30", "robust_zscore"),
        db_path=str(constant_db),
    )
    assert zero_std["status"] == "not_available"
    assert zero_std["missing_reason"] == "zscore_not_available_zero_std"
    assert zero_mad["status"] == "not_available"
    assert zero_mad["missing_reason"] == "robust_zscore_not_available_zero_mad"


def test_new_metadata_module_has_no_forbidden_surfaces():
    text = Path("src/data_quality/historical_percentile_metadata.py").read_text(
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
        "scenario_probability",
        "forecast_path",
        "expected_return",
        "target_price",
        "portfolio_action",
        "trade_signal",
        "target_allocation",
        "buy",
        "sell",
        "hedge",
        "rebalance",
    ):
        assert token not in text


def _spec(source_metric_key):
    return SimpleNamespace(source_metric_key=source_metric_key)


def _payload_spec(
    metric_key,
    source_metric_key,
    kind="percentile",
    direction="higher_is_more_stress",
):
    return percentile.PercentileMetricSpec(
        metric_key,
        source_metric_key,
        metric_key,
        kind,
        direction,
        60,
        kind,
    )


def _latest(
    metric_key,
    *,
    value=1.0,
    value_numeric=None,
    source_series=None,
    status="ok",
    source_badge="official",
    freshness_status="historical",
):
    return {
        "metric_key": metric_key,
        "value": value,
        "value_numeric": value_numeric,
        "source": "FRED",
        "source_badge": source_badge,
        "source_series": source_series or metric_key.upper(),
        "status": status,
        "freshness_status": freshness_status,
        "observation_date": "2026-06-11",
    }


def _lookback(start_date, count, lookback_window):
    observations = [
        {
            "observation_date": (start_date + timedelta(days=index)).isoformat(),
            "value": float(index + 1),
        }
        for index in range(count)
    ]
    return {
        "observations": observations,
        "lookback_window": lookback_window,
        "lookback_start": observations[0]["observation_date"],
        "lookback_end": observations[-1]["observation_date"],
        "status": "limited_history",
        "observation_count": count,
    }
