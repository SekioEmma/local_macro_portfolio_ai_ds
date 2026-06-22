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


__all__ = [
    "SearchGuardResult",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchRuntimePolicy",
]
