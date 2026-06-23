from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app_backend.schemas.commodity_quote import CommodityQuoteSnapshot
from app_backend.schemas.search_external import (
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app_backend.services.commodity_quote_service import CommodityQuoteService


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_SOURCE = (
    _REPO_ROOT / "src/app_backend/services/commodity_quote_service.py"
)


def _result(
    *,
    url: str = "https://www.reuters.com/markets/commodities/brent",
    title: str = "Brent crude settles higher",
    snippet: str = "Brent crude oil settled at $82.50 per barrel on Tuesday.",
    domain: str = "reuters.com",
) -> SearchResult:
    return SearchResult(url=url, title=title, snippet=snippet, domain=domain)


def _response(
    results: list[SearchResult] | None = None,
    *,
    search_available: bool = True,
    guard_passed: bool = True,
) -> SearchResponse:
    return SearchResponse(
        results=results or [],
        search_available=search_available,
        guard_passed=guard_passed,
    )


class RecordingSearch:
    def __init__(
        self,
        response: SearchResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[SearchRequest] = []
        self.response = response if response is not None else _response()
        self.error = error

    def __call__(self, request: SearchRequest) -> SearchResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def _service(search: RecordingSearch) -> CommodityQuoteService:
    return CommodityQuoteService(search_callable=search)


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
def test_commodity_snapshot_is_frozen_and_forbids_extra():
    snapshot = CommodityQuoteSnapshot(
        benchmark="brent",
        status="unavailable",
        reason_code="no_safe_price_match",
    )
    with pytest.raises(ValidationError):
        CommodityQuoteSnapshot(
            benchmark="brent",
            status="unavailable",
            reason_code="no_safe_price_match",
            api_key="forbidden",
        )
    with pytest.raises(ValidationError):
        snapshot.status = "observed"


def test_commodity_schema_fields_exclude_sensitive_surfaces():
    forbidden = {
        "snippet",
        "raw_payload",
        "raw_error",
        "headers",
        "api_key",
        "holdings",
        "account",
        "position",
        "transaction",
        "local_path",
    }
    assert not forbidden.intersection(CommodityQuoteSnapshot.model_fields)


def test_observed_snapshot_requires_value_unit_and_source():
    with pytest.raises(ValidationError):
        CommodityQuoteSnapshot(benchmark="brent", status="observed")


def test_unavailable_snapshot_must_not_carry_value():
    with pytest.raises(ValidationError):
        CommodityQuoteSnapshot(
            benchmark="brent",
            status="unavailable",
            reason_code="no_safe_price_match",
            value_usd_per_barrel=80.0,
            unit="USD/bbl",
        )


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def test_construction_makes_no_search_call():
    search = RecordingSearch()
    CommodityQuoteService(search_callable=search)
    assert search.calls == []


# --------------------------------------------------------------------------
# Valid observed paths
# --------------------------------------------------------------------------
def test_brent_reuters_valid_snippet_is_observed():
    search = RecordingSearch(_response([_result()]))

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "observed"
    assert snapshot.reason_code is None
    assert snapshot.benchmark == "brent"
    assert snapshot.value_usd_per_barrel == 82.50
    assert snapshot.unit == "USD/bbl"
    assert snapshot.source_url == (
        "https://reuters.com/markets/commodities/brent"
    )
    assert snapshot.source_domain == "reuters.com"
    assert snapshot.source_title == "Brent crude settles higher"


def test_wti_bloomberg_valid_snippet_is_observed():
    result = _result(
        url="https://www.bloomberg.com/energy/wti",
        title="WTI crude holds gains",
        snippet="WTI crude oil traded at $78.20 a barrel in New York.",
        domain="bloomberg.com",
    )
    search = RecordingSearch(_response([result]))

    snapshot = _service(search).quote("wti")

    assert snapshot.status == "observed"
    assert snapshot.benchmark == "wti"
    assert snapshot.value_usd_per_barrel == 78.20
    assert snapshot.source_domain == "bloomberg.com"


def test_oilprice_valid_snippet_is_observed():
    result = _result(
        url="https://oilprice.com/Energy/Crude-Oil/brent-today",
        title="Brent steady",
        snippet="Brent crude oil was quoted at USD 83.10 per barrel.",
        domain="oilprice.com",
    )
    search = RecordingSearch(_response([result]))

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "observed"
    assert snapshot.value_usd_per_barrel == 83.10
    assert snapshot.source_domain == "oilprice.com"


@pytest.mark.parametrize("raw", [" Brent ", "BRENT", "brent\t"])
def test_benchmark_normalization_for_brent(raw):
    search = RecordingSearch(_response([_result()]))

    snapshot = _service(search).quote(raw)

    assert snapshot.benchmark == "brent"
    assert snapshot.status == "observed"


# --------------------------------------------------------------------------
# Fixed query / max_results / domain filter
# --------------------------------------------------------------------------
def test_brent_uses_fixed_query_max_results_and_domains():
    search = RecordingSearch(_response([_result()]))

    _service(search).quote("brent")

    assert len(search.calls) == 1
    request = search.calls[0]
    assert request.query == "Brent crude oil price USD per barrel"
    assert request.max_results == 3
    assert request.domain_filter == [
        "reuters.com",
        "bloomberg.com",
        "oilprice.com",
    ]


def test_wti_uses_fixed_query():
    search = RecordingSearch(_response([]))

    _service(search).quote("wti")

    assert search.calls[0].query == "WTI crude oil price USD per barrel"
    assert search.calls[0].max_results == 3


# --------------------------------------------------------------------------
# Unsupported benchmark
# --------------------------------------------------------------------------
def test_unsupported_benchmark_calls_nothing():
    search = RecordingSearch(_response([_result()]))

    snapshot = _service(search).quote("gold")

    assert search.calls == []
    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "unsupported_benchmark"
    assert snapshot.value_usd_per_barrel is None


# --------------------------------------------------------------------------
# Search-layer failures
# --------------------------------------------------------------------------
def test_search_exception_is_unavailable_without_leak():
    search = RecordingSearch(error=RuntimeError("raw secret detail"))

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "search_unavailable"
    assert "raw secret detail" not in snapshot.model_dump_json()


def test_guard_blocked_response_is_blocked_search():
    search = RecordingSearch(
        _response([], search_available=False, guard_passed=False)
    )

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "blocked_search"


def test_search_unavailable_response_is_search_unavailable():
    search = RecordingSearch(
        _response([], search_available=False, guard_passed=True)
    )

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "search_unavailable"


# --------------------------------------------------------------------------
# URL secondary defense
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "ftp://reuters.com/brent",
        "http://user:pass@reuters.com/brent",
        "https://reuters.com/brent?token=secret",
        "https://reuters.com/brent#frag",
        "https://evilreuters.com/brent",
        "not-a-url",
        "https://reddit.com/r/oil/brent",
    ],
)
def test_unsafe_urls_are_skipped(url):
    result = _result(url=url)
    search = RecordingSearch(_response([result]))

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "no_safe_price_match"
    assert snapshot.source_url is None


# --------------------------------------------------------------------------
# Strict price extraction
# --------------------------------------------------------------------------
def test_snippet_without_benchmark_name_is_no_safe_match():
    result = _result(
        title="Crude settles higher",
        snippet="Crude oil settled at $82.50 per barrel on Tuesday.",
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "no_safe_price_match"


def test_snippet_without_usd_is_no_safe_match():
    result = _result(
        snippet="Brent crude oil settled at 82.50 per barrel on Tuesday.",
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "no_safe_price_match"


def test_snippet_without_barrel_unit_is_no_safe_match():
    result = _result(
        snippet="Brent crude oil settled at $82.50 on Tuesday.",
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "no_safe_price_match"


def test_price_range_is_no_safe_match():
    result = _result(
        snippet="Brent crude oil traded at $80 to $85 per barrel.",
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "no_safe_price_match"


@pytest.mark.parametrize(
    "snippet",
    [
        "Brent crude oil is expected to reach $90 per barrel.",
        "Brent crude oil price target raised to $95 per barrel.",
        "Analysts forecast Brent at $88 per barrel.",
        "Brent crude oil could hit $100 per barrel.",
    ],
)
def test_forecast_language_is_no_safe_match(snippet):
    result = _result(snippet=snippet)
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "no_safe_price_match"


def test_brent_and_wti_in_same_text_is_ambiguous():
    result = _result(
        snippet=(
            "Brent crude oil settled at $82.50 per barrel while WTI rose."
        ),
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "ambiguous_price_match"


def test_multiple_prices_is_ambiguous():
    result = _result(
        snippet=(
            "Brent crude oil settled at $82.50 per barrel, up from $80.10."
        ),
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.reason_code == "ambiguous_price_match"


def test_first_strict_match_wins_after_skipping_invalid():
    skip = _result(
        url="https://evilreuters.com/brent",
        snippet="Brent crude oil settled at $50.00 per barrel.",
    )
    good = _result(
        url="https://www.reuters.com/markets/brent",
        snippet="Brent crude oil settled at $82.50 per barrel.",
    )
    search = RecordingSearch(_response([skip, good]))

    snapshot = _service(search).quote("brent")

    assert snapshot.status == "observed"
    assert snapshot.value_usd_per_barrel == 82.50
    assert snapshot.source_domain == "reuters.com"


# --------------------------------------------------------------------------
# Output hygiene
# --------------------------------------------------------------------------
def test_output_excludes_snippet_and_secret_like_text():
    result = _result(
        snippet=(
            "Brent crude oil settled at $82.50 per barrel. "
            "SNIPPETMARKER Authorization Bearer tvly-secretkey"
        ),
    )
    snapshot = _service(_service_search(result)).quote("brent")

    serialized = snapshot.model_dump_json()
    assert snapshot.status == "observed"
    assert "SNIPPETMARKER" not in serialized
    assert "tvly-secretkey" not in serialized
    assert "Authorization" not in serialized


def test_source_domain_is_derived_from_url_not_provider_field():
    result = _result(
        url="https://markets.reuters.com/brent",
        domain="evil.example",
        snippet="Brent crude oil settled at $82.50 per barrel.",
    )
    snapshot = _service(_service_search(result)).quote("brent")

    assert snapshot.status == "observed"
    assert snapshot.source_domain == "markets.reuters.com"
    assert "evil.example" not in snapshot.model_dump_json()


# --------------------------------------------------------------------------
# Source-level boundary
# --------------------------------------------------------------------------
def test_commodity_service_source_has_no_forbidden_imports():
    source = _SERVICE_SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "import httpx",
        "import requests",
        "import aiohttp",
        "import os",
        "os.environ",
        "os.getenv",
        "sqlite3",
        "FastAPI",
        "app_backend.main",
    ):
        assert forbidden not in source


def _service_search(result: SearchResult) -> RecordingSearch:
    return RecordingSearch(_response([result]))
