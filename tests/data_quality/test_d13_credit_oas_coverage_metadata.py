import json
from datetime import date
from pathlib import Path

from data_quality import historical_percentile_metrics as percentile
from tests.helpers.market_history_fixtures import seed_market_history_series_for_tests

_REPO_ROOT = Path(__file__).resolve().parents[2]


COVERAGE_METADATA_KEYS = (
    "history_coverage_status",
    "provider_rebuild_status",
    "normalization_availability",
    "coverage_diagnostics",
    "credit_reference_role",
    "substitution_policy",
    "long_history_reference_status",
)


def test_coverage_metadata_fields_present_on_eligible_and_blocked_rows(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2020, 1, 1), 1900)

    eligible = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )
    blocked = percentile.build_metric_payload(
        _spec("dfii10_percentile", "dfii10"),
        db_path=str(tmp_path / "missing.sqlite3"),
    )

    for row in (eligible, blocked):
        for key in COVERAGE_METADATA_KEYS:
            assert key in row
            assert key in row["component_contributions"]


def test_sanitized_d13_context_carries_coverage_metadata(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "vix", date(2020, 1, 1), 1900)

    row = percentile.build_metric_payload(
        _spec("vix_percentile", "vix"),
        db_path=str(db_path),
    )
    row["module"] = "historical_risk_percentile"

    sanitized = percentile.sanitized_d13_context(row)

    for key in COVERAGE_METADATA_KEYS:
        assert key in sanitized


def test_high_yield_oas_1094_coverage_days_is_below_exact_gate(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2023, 6, 13), 1095)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread", "percentile"),
        db_path=str(db_path),
    )

    _assert_below_gate_oas_row(row, "BAMLH0A0HYM2")


def test_investment_grade_oas_1094_coverage_days_is_below_exact_gate(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "investment_grade_spread", date(2023, 6, 13), 1095)

    row = percentile.build_metric_payload(
        _spec(
            "investment_grade_spread_percentile",
            "investment_grade_spread",
            "percentile",
        ),
        db_path=str(db_path),
    )

    _assert_below_gate_oas_row(row, "BAMLC0A0CM")


def test_exact_3y_gate_is_not_relaxed_and_naturally_clears(tmp_path):
    blocked_db = tmp_path / "blocked.sqlite3"
    limited_db = tmp_path / "limited.sqlite3"
    _insert_series(blocked_db, "high_yield_spread", date(2023, 6, 13), 1095)
    _insert_series(limited_db, "high_yield_spread", date(2023, 6, 13), 1096)

    blocked = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread"),
        db_path=str(blocked_db),
    )
    limited = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread"),
        db_path=str(limited_db),
    )

    assert blocked["status"] == "insufficient_history"
    assert blocked["history_coverage_status"] == "below_exact_gate"
    assert blocked["coverage_diagnostics"]["coverage_days"] == 1094
    assert blocked["coverage_diagnostics"]["days_short"] == 1
    assert limited["history_quality_status"] == "limited_history"
    assert limited["lookback_window"] == "3Y rolling limited_history"
    assert limited["history_coverage_status"] == "limited_history"
    assert limited["coverage_diagnostics"]["coverage_days"] == 1095
    assert limited["coverage_diagnostics"]["days_short"] == 0


def test_near_gate_oas_current_level_available_but_normalization_unavailable(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2023, 6, 13), 1095)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_robust_zscore", "high_yield_spread", "robust_zscore"),
        db_path=str(db_path),
    )

    assert row["input_evidence"][0]["metric_key"] == "high_yield_spread"
    assert row["input_evidence"][0]["value"] == 1095.0
    assert row["normalization_availability"] == {
        "percentile_available": False,
        "zscore_available": False,
        "robust_zscore_available": False,
        "current_level_available": True,
        "long_history_reference_available": False,
    }


def test_baa10y_policy_is_proxy_reference_not_oas_substitute():
    assert percentile._credit_reference_role("BAA10Y") == "long_history_credit_proxy_reference"
    assert percentile._substitution_policy("BAA10Y") == "proxy_reference_not_oas_substitute"
    assert percentile._long_history_reference_status("BAA10Y") == "available_proxy_reference"
    assert percentile._provider_rebuild_status("BAA10Y") == "reproducible_long_history"
    assert percentile._credit_reference_role("BAA10Y") != "primary_oas_series"
    assert percentile._substitution_policy("high_yield_spread") == "no_substitution"
    assert percentile._substitution_policy("investment_grade_spread") == "no_substitution"


def test_below_gate_metadata_does_not_relax_ai_context(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "investment_grade_spread", date(2023, 6, 13), 1095)

    row = percentile.build_metric_payload(
        _spec("investment_grade_spread_zscore", "investment_grade_spread", "zscore"),
        db_path=str(db_path),
    )
    row["module"] = "historical_risk_percentile"
    index = percentile.build_evidence_index([row])

    assert row["ai_context_allowed"] is False
    assert row["trigger_eligibility"] == "not_eligible"
    assert index.available_d13_context([row["metric_key"]]) == []
    missing = index.missing_d13_context([row["metric_key"]])
    assert missing[0]["history_coverage_status"] == "below_exact_gate"


def test_coverage_metadata_does_not_inject_forbidden_language(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2023, 6, 13), 1095)

    row = percentile.build_metric_payload(
        _spec("high_yield_spread_percentile", "high_yield_spread"),
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


def test_d13_production_file_has_no_forbidden_surfaces_after_coverage_metadata():
    text = (_REPO_ROOT / "src/data_quality/historical_percentile_metrics.py").read_text(
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
        "buy",
        "sell",
        "hedge",
        "rebalance",
    ):
        assert token not in text


def _assert_below_gate_oas_row(row, expected_series):
    assert row["status"] == "insufficient_history"
    assert row["history_quality_status"] == "insufficient_history"
    assert row["history_coverage_status"] == "below_exact_gate"
    assert row["provider_rebuild_status"] == "provider_rebuild_limited"
    assert row["normalization_availability"] == {
        "percentile_available": False,
        "zscore_available": False,
        "robust_zscore_available": False,
        "current_level_available": True,
        "long_history_reference_available": False,
    }
    assert row["coverage_diagnostics"]["required_days"] == 1095
    assert row["coverage_diagnostics"]["coverage_days"] == 1094
    assert row["coverage_diagnostics"]["days_short"] == 1
    assert row["coverage_diagnostics"]["provider_start_now"] is None
    assert row["coverage_diagnostics"]["provider_end_now"] is None
    assert row["credit_reference_role"] == "primary_oas_series"
    assert row["substitution_policy"] == "no_substitution"
    assert row["long_history_reference_status"] == "unavailable_for_primary_series"
    assert row["source_series"] == expected_series
    assert row["ai_context_allowed"] is False
    assert row["trigger_eligibility"] == "not_eligible"
    assert row["component_contributions"]["history_coverage_status"] == "below_exact_gate"
    assert row["component_contributions"]["coverage_diagnostics"]["days_short"] == 1


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


def _insert_series(db_path, metric_key, start_date, count):
    source_series = {
        "high_yield_spread": "BAMLH0A0HYM2",
        "investment_grade_spread": "BAMLC0A0CM",
    }.get(metric_key, metric_key.upper())
    seed_market_history_series_for_tests(
        db_path,
        metric_key,
        start_date,
        count,
        source_series=source_series,
    )
