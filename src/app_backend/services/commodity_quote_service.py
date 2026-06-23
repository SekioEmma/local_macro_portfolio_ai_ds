from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from app_backend.schemas.commodity_quote import (
    CommodityQuoteSnapshot,
    CommodityReasonCode,
)
from app_backend.schemas.search_external import SearchRequest, SearchResponse


SearchCallable = Callable[[SearchRequest], SearchResponse]

# Fixed, hard-coded controls for the commodity benchmark search.
_ALLOWED_DOMAINS: tuple[str, ...] = (
    "reuters.com",
    "bloomberg.com",
    "oilprice.com",
)
_MAX_RESULTS = 3
_FIXED_QUERIES: dict[str, str] = {
    "brent": "Brent crude oil price USD per barrel",
    "wti": "WTI crude oil price USD per barrel",
}

# Predictive / non-spot language. Any of these disqualifies a result.
_FORECAST_PATTERN = re.compile(
    r"(?i)\b(forecast|forecasts|forecasted|target|targets|estimate|"
    r"estimates|estimated|expected|expect|expects|may|might|could|"
    r"would|projected|projection|outlook)\b"
)

# Per-barrel unit indicators.
_PER_BARREL_PATTERN = re.compile(
    r"(?i)(per\s+barrel|a\s+barrel|/\s*bbl|per\s+bbl|/\s*barrel)"
)

# A USD-anchored price range (e.g. "$70-$75", "USD 70 to 75").
_RANGE_PATTERN = re.compile(
    r"(?i)(?:\$|usd|us\$)\s?\d+(?:\.\d+)?\s*(?:-|–|—|to)\s*"
    r"(?:\$|usd|us\$)?\s?\d+(?:\.\d+)?"
)

# Single USD-anchored amounts.
_USD_AMOUNT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(?:\$|us\$)\s?(\d+(?:\.\d+)?)"),
    re.compile(r"(?i)\busd\s?(\d+(?:\.\d+)?)"),
    re.compile(r"(?i)(\d+(?:\.\d+)?)\s?(?:usd|us\$|dollars)\b"),
)

_BRENT_PATTERN = re.compile(r"(?i)\bbrent\b")
_WTI_PATTERN = re.compile(
    r"(?i)(\bwti\b|west\s+texas\s+intermediate)"
)


class CommodityQuoteService:
    """Guarded Brent / WTI commodity quote service.

    Depends only on an injected ``search_callable``. It performs no network,
    file, database, cache, or log I/O, and reads no environment or config.
    """

    def __init__(self, *, search_callable: SearchCallable) -> None:
        self._search_callable = search_callable

    def quote(self, benchmark: str) -> CommodityQuoteSnapshot:
        normalized = str(benchmark).strip().lower()
        if normalized not in _FIXED_QUERIES:
            return _unavailable(normalized, "unsupported_benchmark")

        request = SearchRequest(
            query=_FIXED_QUERIES[normalized],
            max_results=_MAX_RESULTS,
            domain_filter=list(_ALLOWED_DOMAINS),
        )
        try:
            response = self._search_callable(request)
        except Exception:
            return _unavailable(normalized, "search_unavailable")

        if not isinstance(response, SearchResponse):
            return _unavailable(normalized, "search_unavailable")
        if not response.guard_passed:
            return _unavailable(normalized, "blocked_search")
        if not response.search_available:
            return _unavailable(normalized, "search_unavailable")

        saw_ambiguous = False
        for result in response.results:
            safe = _safe_source_url(result.url)
            if safe is None:
                continue
            safe_url, hostname = safe
            text = f"{result.title}\n{result.snippet}"
            outcome, value = _classify_result(text, normalized)
            if outcome == "match" and value is not None:
                return CommodityQuoteSnapshot(
                    benchmark=normalized,
                    value_usd_per_barrel=value,
                    unit="USD/bbl",
                    status="observed",
                    reason_code=None,
                    source_url=safe_url,
                    source_domain=hostname,
                    source_title=result.title,
                )
            if outcome == "ambiguous":
                saw_ambiguous = True

        if saw_ambiguous:
            return _unavailable(normalized, "ambiguous_price_match")
        return _unavailable(normalized, "no_safe_price_match")


def _unavailable(
    benchmark: str,
    reason_code: CommodityReasonCode,
) -> CommodityQuoteSnapshot:
    return CommodityQuoteSnapshot(
        benchmark=benchmark,
        value_usd_per_barrel=None,
        unit=None,
        status="unavailable",
        reason_code=reason_code,
        source_url=None,
        source_domain=None,
        source_title=None,
    )


def _classify_result(
    text: str,
    benchmark: str,
) -> tuple[str, float | None]:
    """Return ("match", value) | ("ambiguous", None) | ("no_match", None)."""
    mentions_brent = bool(_BRENT_PATTERN.search(text))
    mentions_wti = bool(_WTI_PATTERN.search(text))
    if benchmark == "brent":
        has_target, has_other = mentions_brent, mentions_wti
    else:
        has_target, has_other = mentions_wti, mentions_brent

    if not has_target:
        return ("no_match", None)
    if has_other:
        return ("ambiguous", None)
    if _FORECAST_PATTERN.search(text):
        return ("no_match", None)
    if not _PER_BARREL_PATTERN.search(text):
        return ("no_match", None)
    if _RANGE_PATTERN.search(text):
        return ("no_match", None)

    values = _usd_amounts(text)
    if len(values) == 0:
        return ("no_match", None)
    if len(values) > 1:
        return ("ambiguous", None)
    return ("match", next(iter(values)))


def _usd_amounts(text: str) -> set[float]:
    values: set[float] = set()
    for pattern in _USD_AMOUNT_PATTERNS:
        for match in pattern.finditer(text):
            try:
                values.add(round(float(match.group(1)), 4))
            except (TypeError, ValueError):
                continue
    return values


def _safe_source_url(url: str) -> tuple[str, str] | None:
    """Secondary URL defense. Returns (clean_url, hostname) or None.

    Rejects non-http(s) schemes, userinfo, query strings, and fragments, and
    only accepts the three allowed domains or their legitimate subdomains. The
    hostname is derived from the URL itself and never from any provider field.
    """
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname is None:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.query or parsed.fragment:
        return None
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if not any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in _ALLOWED_DOMAINS
    ):
        return None
    clean_url = urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))
    return clean_url, hostname


__all__ = [
    "CommodityQuoteService",
    "SearchCallable",
]
