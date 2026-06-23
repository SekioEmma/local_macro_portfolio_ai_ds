from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchRuntimePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    search_enabled: bool = False
    provider_network_enabled: bool = False
    user_controlled_switch_enabled: bool = False
    single_request_user_approved: bool = False
    query_sanitizer_passed: bool = False
    domain_allowlist_enforced: bool = False
    response_guard_required: bool = False
    budget_within_limit: bool = False

    save_raw_query: bool = False
    save_raw_html: bool = False
    allow_holdings_in_query: bool = False
    allow_position_in_query: bool = False
    allow_account_in_query: bool = False
    allow_local_path_in_query: bool = False


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    max_results: int = 5
    domain_filter: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    snippet: str
    domain: str


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult] = Field(default_factory=list)
    search_available: bool
    guard_passed: bool


class SearchGuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    blocking_flags: list[str] = Field(default_factory=list)


class TavilySearchApiRequest(BaseModel):
    """Client-facing request for the guarded search route.

    The client may only supply the query, a result cap, an optional domain
    narrowing list, and an explicit per-request external-search confirmation.
    It must not supply runtime policy, budget, provider keys, transport
    endpoints, allowlist/blocklist, or any dangerous-permission fields.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)
    domain_filter: list[str] = Field(default_factory=list)
    confirm_external_search: bool = False


__all__ = [
    "SearchGuardResult",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchRuntimePolicy",
    "TavilySearchApiRequest",
]
