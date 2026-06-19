from __future__ import annotations

import importlib.util
from pathlib import Path

from data_providers import alpha_vantage_provider
from data_providers.source_registry import prefer_source


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ingest_alpha_vantage_market_proxy_history.py"
)
SPEC = importlib.util.spec_from_file_location(
    "ingest_alpha_vantage_market_proxy_history", SCRIPT
)
assert SPEC and SPEC.loader
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


def test_api_key_loads_from_environment(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "environment-only")
    assert alpha_vantage_provider.load_alpha_vantage_api_key() == "environment-only"


def test_proxy_rows_use_commercial_fallback_policy():
    rows = ingest.normalize_proxy_history(
        {
            "status": "ok",
            "symbol": "HYG",
            "timestamp": "2026-06-19T00:00:00+00:00",
            "observations": [
                {"date": "2026-06-18", "close": "80.25"},
                {"date": "2026-06-17", "close": None},
            ],
        },
        symbol="HYG",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["source_badge"] == "commercial_api_fallback"
    assert row["lineage"]["trigger_eligibility"] == "support_only"
    assert "cannot replace true breadth" in row["lineage"]["interpretation_boundary"]


def test_fallback_priority_below_official_sources():
    assert prefer_source("official", "commercial_api_fallback") is True
    assert prefer_source("official_fallback", "commercial_api_fallback") is True
    assert prefer_source("dataset_official", "commercial_api_fallback") is True
    assert prefer_source("commercial_api_fallback", "official_fallback") is False


def test_rate_limit_stops_remaining_requests():
    calls = []

    def fetcher(symbol, outputsize):
        calls.append((symbol, outputsize))
        return {
            "status": "error",
            "error": "Alpha Vantage rate limit reached",
        }

    summary = ingest.build_ingest_summary(
        symbols=["SPY", "QQQ"],
        outputsize="compact",
        live=True,
        fetcher=fetcher,
    )
    assert calls == [("SPY", "compact")]
    assert summary["rate_limit_stop"] is True


def test_supported_proxy_universe():
    assert set(ingest.PROXY_SYMBOLS) == {
        "SPY",
        "QQQ",
        "RSP",
        "TLT",
        "GLD",
        "HYG",
        "LQD",
        "SHY",
    }
