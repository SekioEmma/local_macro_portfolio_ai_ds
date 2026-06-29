from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app_backend.services.macro_news_relevance_filter import (
    DEFAULT_RELEVANCE_THRESHOLD,
    ScoredResult,
    filter_results,
    score_result,
)


_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _FakeResult:
    """Mirrors SearchResult duck-type used by the filter."""

    url: str
    title: str
    snippet: str
    domain: str
    published_at: str | None = None


# ---------------------------------------------------------------------------
# score_result
# ---------------------------------------------------------------------------


def test_score_trusted_domain_alone_boosts_below_threshold():
    score = score_result(
        title="Markets update", snippet="Yields rose.",
        url="https://reuters.com/x", domain="reuters.com", now=_NOW,
    )
    # 15 from reuters.com, nothing else
    assert score == 15


def test_score_high_value_title_keyword_pushes_above_threshold():
    score = score_result(
        title="FOMC holds rates steady", snippet="Powell speaks tomorrow.",
        url="https://reuters.com/x", domain="reuters.com", now=_NOW,
    )
    # fomc (15 title) + powell (15 snippet but counts as title here? no, snippet)
    # title contains 'fomc' -> +15; snippet contains 'powell' -> +8;
    # plus reuters domain +15 = 38
    assert score >= 30


def test_score_speculation_in_title_penalized():
    score_speculative = score_result(
        title="Analyst predicts CPI could surge",
        snippet="market commentary",
        url="https://reuters.com/x", domain="reuters.com", now=_NOW,
    )
    score_factual = score_result(
        title="CPI release confirms inflation cooling",
        snippet="market commentary",
        url="https://reuters.com/x", domain="reuters.com", now=_NOW,
    )
    assert score_factual > score_speculative


def test_score_subdomain_inherits_parent_trust():
    score = score_result(
        title="Bond markets calm", snippet="Yields steady.",
        url="https://markets.reuters.com/bonds", domain="markets.reuters.com",
        now=_NOW,
    )
    # markets.reuters.com inherits reuters.com (+15) via parent match;
    # 'bond' is a medium-value title keyword (+6).
    assert score >= 21


def test_score_federalreserve_gov_gets_top_domain_boost():
    score = score_result(
        title="FOMC statement",
        snippet="Members agreed to hold rates.",
        url="https://federalreserve.gov/x", domain="federalreserve.gov",
        now=_NOW,
    )
    # fomc title +15, federalreserve.gov +20
    assert score >= 35


def test_score_caps_at_100():
    score = score_result(
        title=" ".join(["FOMC", "PCE", "CPI", "Treasury", "Powell"] * 5),
        snippet="rate cut rate hike yield curve hy oas inflation",
        url="https://federalreserve.gov/x", domain="federalreserve.gov",
        now=_NOW.isoformat(),
    )
    assert score == 100


def test_score_freshness_under_24h_boost():
    published = (_NOW - timedelta(hours=4)).isoformat()
    fresh = score_result(
        title="market", snippet="x", url="https://example.com/x", domain="example.com",
        published_at=published, now=_NOW,
    )
    stale = score_result(
        title="market", snippet="x", url="https://example.com/x", domain="example.com",
        published_at=(_NOW - timedelta(days=60)).isoformat(), now=_NOW,
    )
    assert fresh - stale == 25


def test_score_freshness_7d_boost():
    published = (_NOW - timedelta(days=3)).isoformat()
    score = score_result(
        title="x", snippet="x", url="https://example.com/x", domain="example.com",
        published_at=published, now=_NOW,
    )
    assert score == 15  # only the 7d freshness boost, no other contributions


def test_score_freshness_30d_boost():
    published = (_NOW - timedelta(days=15)).isoformat()
    score = score_result(
        title="x", snippet="x", url="https://example.com/x", domain="example.com",
        published_at=published, now=_NOW,
    )
    assert score == 5


def test_score_future_dated_treated_as_no_freshness_boost():
    score = score_result(
        title="x", snippet="x", url="https://example.com/x", domain="example.com",
        published_at=(_NOW + timedelta(days=1)).isoformat(), now=_NOW,
    )
    assert score == 0


def test_score_malformed_date_silently_skipped():
    score = score_result(
        title="x", snippet="x", url="https://example.com/x", domain="example.com",
        published_at="not-a-date", now=_NOW,
    )
    assert score == 0


def test_score_handles_iso_with_z_suffix():
    score = score_result(
        title="x", snippet="x", url="https://example.com/x", domain="example.com",
        published_at="2026-06-29T08:00:00Z", now=_NOW,
    )
    # 4h fresh
    assert score == 25


def test_score_unknown_domain_no_boost():
    score = score_result(
        title="x", snippet="x", url="https://unknown.example/y", domain="unknown.example",
        now=_NOW,
    )
    assert score == 0


def test_score_uses_domain_field_first_then_falls_back_to_url():
    score_from_domain = score_result(
        title="x", snippet="x", url="https://malicious.tld/y", domain="reuters.com",
        now=_NOW,
    )
    score_from_url = score_result(
        title="x", snippet="x", url="https://reuters.com/y", domain="",
        now=_NOW,
    )
    assert score_from_domain == 15
    assert score_from_url == 15


# ---------------------------------------------------------------------------
# filter_results
# ---------------------------------------------------------------------------


def test_filter_drops_below_threshold():
    results = [
        _FakeResult("https://reuters.com/x", "Markets update", "yields rose.", "reuters.com"),  # 15
        _FakeResult("https://reuters.com/y", "FOMC holds steady", "", "reuters.com"),  # 30
        _FakeResult("https://example.com/z", "random news", "", "example.com"),  # 0
    ]
    kept, dropped = filter_results(results, threshold=DEFAULT_RELEVANCE_THRESHOLD, now=_NOW)

    assert dropped == 2
    assert [r.title for r in kept] == ["FOMC holds steady"]
    assert kept[0].score >= DEFAULT_RELEVANCE_THRESHOLD
    assert kept[0].passed is True


def test_filter_preserves_input_order_among_kept():
    results = [
        _FakeResult("https://reuters.com/a", "Fed signals rate cut path", "", "reuters.com"),  # high
        _FakeResult("https://federalreserve.gov/b", "FOMC release", "", "federalreserve.gov"),  # higher
        _FakeResult("https://reuters.com/c", "CPI cools", "", "reuters.com"),
    ]
    kept, _ = filter_results(results, now=_NOW)
    assert [r.url for r in kept] == [r.url for r in results]


def test_filter_empty_input_returns_empty():
    kept, dropped = filter_results([])
    assert kept == []
    assert dropped == 0


def test_filter_invalid_threshold_raises():
    with pytest.raises(ValueError):
        filter_results([], threshold=-1)
    with pytest.raises(ValueError):
        filter_results([], threshold=101)


def test_filter_accepts_dict_input_not_just_dataclass():
    results = [
        {
            "url": "https://reuters.com/x",
            "title": "FOMC holds",
            "snippet": "",
            "domain": "reuters.com",
        }
    ]
    kept, _ = filter_results(results, now=_NOW)
    assert len(kept) == 1
    assert isinstance(kept[0], ScoredResult)


def test_filter_carries_published_at_through():
    results = [
        _FakeResult(
            "https://reuters.com/x",
            "FOMC release",
            "",
            "reuters.com",
            published_at="2026-06-29T08:00:00Z",
        )
    ]
    kept, _ = filter_results(results, now=_NOW)
    assert kept[0].published_at == "2026-06-29T08:00:00Z"


def test_filter_threshold_zero_passes_everything():
    results = [
        _FakeResult("https://nowhere.example/x", "random", "", "nowhere.example"),
    ]
    kept, dropped = filter_results(results, threshold=0, now=_NOW)
    assert dropped == 0
    assert len(kept) == 1
