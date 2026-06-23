
from data_providers import yfinance_history_provider as provider


def test_fake_downloader_single_symbol_normalizes_adjusted_close():
    raw = {
        "SPY": [
            {"date": "2026-01-01 00:00:00-05:00", "Adj Close": 100.5, "Close": 101.0},
        ]
    }
    symbol_map = {
        "SPY": {
            "metric_key": "spy_proxy",
            "source_badge": "proxy",
            "metric_kind": "proxy",
            "unit": "price",
            "interpretation_hint": "ETF proxy.",
        }
    }

    normalized = provider.normalize_yfinance_history(raw, symbol_map, fetched_at="2026-01-02T00:00:00+00:00")

    assert normalized["status"] == "ok"
    assert normalized["record_count"] == 1
    record = normalized["records"][0]
    assert record["metric_key"] == "spy_proxy"
    assert record["observation_date"] == "2026-01-01"
    assert record["value"] == 100.5
    assert record["value_field"] == "Adjusted Close"
    assert record["source_badge"] == "proxy"
    assert record["provider"] == "yfinance"
    assert record["source_series"] == "SPY"


def test_fake_downloader_multi_symbol_normalizes_records():
    fetched = provider.fetch_yfinance_batch_history(
        ["SPY", "QQQ"],
        downloader=lambda **kwargs: {
            "SPY": [{"date": "2026-01-01", "Adj Close": 100.0}],
            "QQQ": [{"date": "2026-01-01", "Adj Close": 200.0}],
        },
    )
    symbol_map = {
        "SPY": _config("spy_proxy", "proxy"),
        "QQQ": _config("qqq_proxy", "proxy"),
    }

    normalized = provider.normalize_yfinance_history(
        fetched["raw_data"],
        symbol_map,
        fetched_at=fetched["generated_at"],
    )

    assert fetched["status"] == "ok"
    assert {item["metric_key"] for item in normalized["records"]} == {"spy_proxy", "qqq_proxy"}


def test_close_fallback_and_nan_rows_are_skipped():
    raw = {
        "SPY": [
            {"date": "2026-01-01", "Adj Close": float("nan"), "Close": 101.0},
            {"date": "2026-01-02", "Adj Close": None, "Close": float("nan")},
        ]
    }

    normalized = provider.normalize_yfinance_history(
        raw,
        {"SPY": _config("spy_proxy", "proxy")},
        fetched_at="2026-01-03T00:00:00+00:00",
    )

    assert normalized["record_count"] == 1
    record = normalized["records"][0]
    assert record["value"] == 101.0
    assert record["value_field"] == "Close"
    assert "Close used" in record["interpretation_hint"]


def test_malformed_data_returns_structured_error():
    normalized = provider.normalize_yfinance_history(
        {"SPY": "not rows"},
        {"SPY": _config("spy_proxy", "proxy")},
    )

    assert normalized["status"] == "error"
    assert normalized["errors"][0]["symbol"] == "SPY"


def test_fetch_error_is_structured():
    fetched = provider.fetch_yfinance_batch_history(
        ["SPY"],
        downloader=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("rate limited")),
    )

    assert fetched["status"] == "error"
    assert "rate limited" in fetched["error"]


def test_build_market_observations_is_safe_and_compact():
    records = [
        {
            "metric_key": "sp500",
            "symbol": "^GSPC",
            "observation_date": "2026-01-01",
            "value": 100.0,
            "value_text": "100.0000",
            "unit": "index",
            "source_badge": "unofficial_fallback",
            "metric_kind": "index",
            "fetched_at": "2026-01-02T00:00:00+00:00",
            "value_field": "Adjusted Close",
            "interpretation_hint": "unofficial fallback",
        },
        {
            "metric_key": "spy_proxy",
            "symbol": "SPY",
            "observation_date": "2026-01-01",
            "value": 100.0,
            "value_text": "100.0000",
            "unit": "price",
            "source_badge": "proxy",
            "metric_kind": "proxy",
            "fetched_at": "2026-01-02T00:00:00+00:00",
            "value_field": "Close",
            "interpretation_hint": "proxy",
        },
    ]

    observations = provider.build_market_observations_from_yfinance(records)
    text = str(observations)

    assert all(item["provider"] == "yfinance" for item in observations)
    assert all(item["ai_context_allowed"] is False for item in observations)
    assert {item["source_badge"] for item in observations} == {"unofficial_fallback", "proxy"}
    lowered = text.lower()
    assert "raw_provider_response" not in lowered
    assert "raw_dataframe" not in lowered
    assert "raw holdings" not in lowered
    assert "raw_prompt" not in lowered
    assert "api_key" not in text.lower()
    assert "holding" not in text.lower()


def _config(metric_key, source_badge):
    return {
        "metric_key": metric_key,
        "source_badge": source_badge,
        "metric_kind": "proxy" if source_badge == "proxy" else "index",
        "unit": "price",
        "interpretation_hint": "Configured fake history.",
    }
