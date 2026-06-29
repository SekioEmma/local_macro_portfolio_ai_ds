"""Phase F1-5 macro news relevance scoring.

A deterministic rule-based filter that scores Tavily search results before
they reach the LLM. Filters out low-signal noise (speculation pieces,
off-topic articles) by combining keyword presence, source trust, and
optional freshness. Each result gets a 0..100 score; results below the
threshold are dropped from the LLM-facing payload.

Approach borrowed from hsliuping/TradingAgents-CN
docs/features/NEWS_FILTERING_SOLUTION_DESIGN.md option 1 (rule filter only —
no sentence-transformers model load). Adapted to a macro-research domain:
the keyword sets are macro-data oriented (Fed / FOMC / CPI / yields) rather
than equities-trading oriented. License: ideas / design only; no source code
copied. See docs/era2_phase_f_plan.md §13.

This module:
- exposes a pure ``score_result`` function (no I/O, no network)
- exposes ``filter_results`` that drops below-threshold entries
- never logs / persists / mutates state

It does NOT:
- read environment / config / files
- call any LLM
- import network clients
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


# Title-presence keywords. A hit in the title adds the full value; a hit
# in the snippet only adds the partial-credit value.
_HIGH_VALUE_KEYWORDS: tuple[str, ...] = (
    "fed",
    "fomc",
    "pce",
    "cpi",
    "treasury",
    "powell",
    "rate cut",
    "rate hike",
    "hy oas",
    "yield curve",
    "fed funds",
    "inflation",
    "unemployment",
    "nonfarm payrolls",
    "nfp",
)
_HIGH_VALUE_TITLE_BOOST = 15
_HIGH_VALUE_SNIPPET_BOOST = 8

# Title-only keywords (broader macro vocabulary).
_MEDIUM_VALUE_KEYWORDS: tuple[str, ...] = (
    "stock",
    "bond",
    "spread",
    "vix",
    "dollar",
    "oil",
    "gold",
    "credit",
    "earnings",
)
_MEDIUM_VALUE_TITLE_BOOST = 6

# Title-only penalty keywords — speculation / opinion-style coverage.
_SPECULATION_KEYWORDS: tuple[str, ...] = (
    "expert says",
    "could rise",
    "could fall",
    "analyst predicts",
    "forecast",
    "may surge",
    "may plunge",
    "set to",
    "set for",
    "poised to",
    "could hit",
)
_SPECULATION_PENALTY = -10

# Trusted source-domain weights. Subdomain matches (e.g. markets.reuters.com)
# inherit the parent's weight.
_TRUSTED_DOMAIN_WEIGHTS: dict[str, int] = {
    "federalreserve.gov": 20,
    "bls.gov": 18,
    "bea.gov": 18,
    "fred.stlouisfed.org": 18,
    "treasury.gov": 18,
    "imf.org": 16,
    "worldbank.org": 16,
    "bis.org": 16,
    "reuters.com": 15,
    "bloomberg.com": 15,
    "wsj.com": 12,
    "ft.com": 12,
}

# Freshness boost (UTC). Older than 30 days → no boost.
_FRESH_BOOST_24H = 25
_FRESH_BOOST_7D = 15
_FRESH_BOOST_30D = 5

# Default threshold; results scoring below this are dropped.
DEFAULT_RELEVANCE_THRESHOLD = 30

# Cap on absolute score so the LLM-facing value is comparable across runs.
_SCORE_MIN = 0
_SCORE_MAX = 100


@dataclass(frozen=True)
class ScoredResult:
    title: str
    snippet: str
    url: str
    domain: str
    score: int
    passed: bool
    published_at: str | None = None


def score_result(
    *,
    title: str,
    snippet: str,
    url: str,
    domain: str,
    published_at: str | None = None,
    now: datetime | None = None,
) -> int:
    """Compute a relevance score for a single search result.

    ``published_at`` may be ``None`` if the underlying provider does not
    surface a publication date; the freshness component then contributes 0.
    The ``now`` parameter is injectable so tests are deterministic.
    """
    score = 0
    score += _freshness_boost(published_at, now)
    score += _keyword_boost(title or "", snippet or "")
    score += _domain_boost(url, domain)
    return max(_SCORE_MIN, min(_SCORE_MAX, score))


def filter_results(
    results: list[Any],
    *,
    threshold: int = DEFAULT_RELEVANCE_THRESHOLD,
    now: datetime | None = None,
) -> tuple[list[ScoredResult], int]:
    """Score every result and split them by threshold.

    Returns ``(kept, dropped_count)``. ``kept`` preserves the input order;
    callers can re-sort by ``.score`` if rank order is preferred. Each
    incoming result may be a SearchResult Pydantic instance, a plain dict,
    or any object with ``url`` / ``title`` / ``snippet`` / ``domain``
    attributes — duck-typed to keep this module decoupled.
    """
    if threshold < 0 or threshold > _SCORE_MAX:
        raise ValueError("threshold must be 0..100")
    kept: list[ScoredResult] = []
    dropped = 0
    for raw in results or []:
        title = _field(raw, "title") or ""
        snippet = _field(raw, "snippet") or ""
        url = _field(raw, "url") or ""
        domain = _field(raw, "domain") or _domain_from_url(url) or ""
        published_at = _field(raw, "published_at") or _field(raw, "published")
        score = score_result(
            title=title,
            snippet=snippet,
            url=url,
            domain=domain,
            published_at=published_at if isinstance(published_at, str) else None,
            now=now,
        )
        scored = ScoredResult(
            title=title,
            snippet=snippet,
            url=url,
            domain=domain,
            score=score,
            passed=score >= threshold,
            published_at=published_at if isinstance(published_at, str) else None,
        )
        if scored.passed:
            kept.append(scored)
        else:
            dropped += 1
    return kept, dropped


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


_ISO_FRACTIONAL_TRAILING = re.compile(r"\.\d+")


def _freshness_boost(published_at: str | None, now: datetime | None) -> int:
    if not published_at or not isinstance(published_at, str):
        return 0
    parsed = _parse_iso8601(published_at)
    if parsed is None:
        return 0
    reference = now if now is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = reference - parsed
    if age.total_seconds() < 0:
        return 0  # future-dated → treat as untrusted timestamp
    days = age.total_seconds() / 86400.0
    if days < 1:
        return _FRESH_BOOST_24H
    if days < 7:
        return _FRESH_BOOST_7D
    if days < 30:
        return _FRESH_BOOST_30D
    return 0


def _parse_iso8601(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _keyword_boost(title: str, snippet: str) -> int:
    title_lc = title.lower()
    snippet_lc = snippet.lower()
    score = 0
    for keyword in _HIGH_VALUE_KEYWORDS:
        if keyword in title_lc:
            score += _HIGH_VALUE_TITLE_BOOST
        elif keyword in snippet_lc:
            score += _HIGH_VALUE_SNIPPET_BOOST
    for keyword in _MEDIUM_VALUE_KEYWORDS:
        if keyword in title_lc:
            score += _MEDIUM_VALUE_TITLE_BOOST
    for keyword in _SPECULATION_KEYWORDS:
        if keyword in title_lc:
            score += _SPECULATION_PENALTY
    return score


def _domain_boost(url: str, domain: str) -> int:
    candidate = (domain or _domain_from_url(url) or "").lower().rstrip(".")
    if candidate.startswith("www."):
        candidate = candidate[4:]
    if not candidate:
        return 0
    weight = _TRUSTED_DOMAIN_WEIGHTS.get(candidate)
    if weight is not None:
        return weight
    # Match parent allowlist domains (e.g. markets.reuters.com → reuters.com).
    for parent, parent_weight in _TRUSTED_DOMAIN_WEIGHTS.items():
        if candidate.endswith("." + parent):
            return parent_weight
    return 0


def _domain_from_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        host = urlparse(url).hostname
    except ValueError:
        return None
    return host.lower() if host else None


__all__ = [
    "DEFAULT_RELEVANCE_THRESHOLD",
    "ScoredResult",
    "filter_results",
    "score_result",
]
