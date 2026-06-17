from data_quality.freshness import calculate_freshness


GENERATED_AT = "2026-06-01T00:00:00+00:00"


def _item(observation_date: str) -> dict:
    return {
        "status": "ok",
        "observation_date": observation_date,
        "source": "FRED",
    }


def _metadata(expected_frequency: str, max_stale_days: int = 1) -> dict:
    return {
        "expected_frequency": expected_frequency,
        "max_stale_days": max_stale_days,
        "source_tier": "official",
        "importance": "core",
    }


def test_daily_freshness_today_or_yesterday_is_fresh():
    today = calculate_freshness(_item("2026-06-01"), _metadata("daily"), GENERATED_AT)
    yesterday = calculate_freshness(_item("2026-05-31"), _metadata("daily"), GENERATED_AT)

    assert today["freshness_status"] == "fresh"
    assert yesterday["freshness_status"] == "fresh"
    assert today["status"] == "ok"


def test_daily_freshness_older_than_max_stale_days_is_stale():
    result = calculate_freshness(_item("2026-05-29"), _metadata("daily"), GENERATED_AT)

    assert result["freshness_status"] == "stale"
    assert result["days_since_observation"] == 3


def test_monthly_freshness_lag_buckets_follow_current_contract():
    normal = calculate_freshness(_item("2026-04-01"), _metadata("monthly"), GENERATED_AT)
    extended = calculate_freshness(_item("2026-03-01"), _metadata("monthly"), GENERATED_AT)
    stale = calculate_freshness(_item("2026-01-01"), _metadata("monthly"), GENERATED_AT)

    assert normal["freshness_status"] == "normal_monthly_lag"
    assert extended["freshness_status"] == "extended_monthly_lag"
    assert stale["freshness_status"] == "stale"


def test_invalid_observation_date_returns_unknown_error():
    result = calculate_freshness(_item("not-a-date"), _metadata("daily"), GENERATED_AT)

    assert result["status"] == "unknown"
    assert result["freshness_status"] == "unknown"
    assert "invalid" in result["error"]


def test_future_observation_date_is_not_treated_as_current():
    result = calculate_freshness(_item("2026-06-02"), _metadata("daily"), GENERATED_AT)

    assert result["status"] == "unknown"
    assert result["freshness_status"] == "unknown"
    assert result["days_since_observation"] == -1
    assert "after generated_at" in result["error"]
