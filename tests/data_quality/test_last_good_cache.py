import json
from datetime import datetime, timedelta, timezone

import pytest

from data_quality import last_good_cache


NOW = datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)


def test_sanitize_metric_key_blocks_path_traversal():
    with pytest.raises(ValueError):
        last_good_cache.sanitize_metric_key("../secret")
    with pytest.raises(ValueError):
        last_good_cache.sanitize_metric_key("nested\\secret")

    assert last_good_cache.sanitize_metric_key("DGS10 5D Avg") == "dgs10_5d_avg"


def test_save_and_load_last_good_success(tmp_path):
    result = last_good_cache.save_last_good(
        _metric("dgs10", value=4.52),
        cache_dir=tmp_path,
        now=NOW,
    )

    assert result["saved"] is True
    loaded = last_good_cache.load_last_good("dgs10", cache_dir=tmp_path, now=NOW)
    metric = loaded["metric"]

    assert loaded["status"] == "usable"
    assert metric["metric_key"] == "dgs10"
    assert metric["value"] == 4.52
    assert metric["ttl_policy"] == "daily"
    assert metric["ttl_days"] == 7


def test_missing_file_returns_unavailable(tmp_path):
    loaded = last_good_cache.load_last_good("dgs10", cache_dir=tmp_path, now=NOW)

    assert loaded["status"] == "unavailable"
    assert loaded["metric"] is None


def test_corrupted_json_returns_error_without_crashing(tmp_path):
    (tmp_path / "dgs10.json").write_text("{not-json", encoding="utf-8")

    loaded = last_good_cache.load_last_good("dgs10", cache_dir=tmp_path, now=NOW)

    assert loaded["status"] == "error"
    assert loaded["metric"] is None
    assert "unreadable" in loaded["error_summary"]


def test_expired_ttl_returns_expired(tmp_path):
    last_good_cache.save_last_good(
        _metric("dgs10", value=4.52),
        cache_dir=tmp_path,
        now=NOW,
    )

    loaded = last_good_cache.load_last_good(
        "dgs10",
        cache_dir=tmp_path,
        now=NOW + timedelta(days=16),
    )

    assert loaded["status"] == "expired"


def test_unknown_frequency_is_conservative_stale(tmp_path):
    last_good_cache.save_last_good(
        _metric("custom_macro_metric", value=1.23),
        cache_dir=tmp_path,
        now=NOW,
    )

    loaded = last_good_cache.load_last_good(
        "custom_macro_metric",
        cache_dir=tmp_path,
        now=NOW,
    )

    assert loaded["status"] == "stale"
    assert loaded["metric"]["ttl_policy"] == "unknown"


@pytest.mark.parametrize("source_badge", ["missing", "research_needed", "search-derived"])
def test_blocked_source_badges_are_not_saved(tmp_path, source_badge):
    result = last_good_cache.save_last_good(
        _metric("dgs10", value=4.52, source_badge=source_badge),
        cache_dir=tmp_path,
        now=NOW,
    )

    assert result["saved"] is False
    assert not list(tmp_path.glob("*.json"))


def test_null_value_is_not_saved(tmp_path):
    result = last_good_cache.save_last_good(
        _metric("dgs10", value=None),
        cache_dir=tmp_path,
        now=NOW,
    )

    assert result["saved"] is False
    assert result["reason"] == "value_missing"
    assert not list(tmp_path.glob("*.json"))


def test_raw_extra_and_api_like_fields_are_not_written(tmp_path):
    metric = _metric("dgs10", value=4.52)
    metric.update(
        {
            "raw_extra": {"api_key": "FAKE_SECRET_TOKEN_MUST_NOT_BE_WRITTEN"},
            "DEEPSEEK_API_KEY": "FAKE_SECRET_TOKEN_MUST_NOT_BE_WRITTEN",
            "holdings": [{"ticker": "RAW_FUND"}],
        }
    )

    last_good_cache.save_last_good(metric, cache_dir=tmp_path, now=NOW)
    body = (tmp_path / "dgs10.json").read_text(encoding="utf-8")

    assert "raw_extra" not in body
    assert "DEEPSEEK_API_KEY" not in body
    assert "FAKE_SECRET_TOKEN_MUST_NOT_BE_WRITTEN" not in body
    assert "RAW_FUND" not in body
    assert set(json.loads(body)) <= set(last_good_cache.SAFE_FIELDS)


def test_list_last_good_cache_counts_errors_and_usable(tmp_path):
    last_good_cache.save_last_good(_metric("dgs10", value=4.52), cache_dir=tmp_path, now=NOW)
    (tmp_path / "broken.json").write_text("{not-json", encoding="utf-8")

    results = last_good_cache.list_last_good_cache(cache_dir=tmp_path, now=NOW)
    statuses = {item["metric_key"]: item["status"] for item in results}

    assert statuses["dgs10"] == "usable"
    assert statuses["broken"] == "error"


def _metric(metric_key, *, value, status="ok", source_badge="official"):
    return {
        "metric_key": metric_key,
        "value": value,
        "value_text": str(value) if value is not None else "missing",
        "unit": "percent",
        "status": status,
        "source": "FRED",
        "source_badge": source_badge,
        "provider": "FRED",
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-04",
        "generated_at": "2026-06-05T00:00:00+00:00",
        "freshness_status": "fresh",
    }
