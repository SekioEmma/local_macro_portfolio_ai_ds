from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchRuntimePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_acknowledged: bool = False
    search_enabled: bool = False
    query_sanitized: bool = False
    domain_allowlist_configured: bool = False
    daily_budget_available: bool = False
    response_guard_enabled: bool = False
    result_classifier_enabled: bool = False
    transport_timeout_set: bool = False

    allow_raw_portfolio_in_query: bool = True
    allow_account_data_in_query: bool = True
    allow_pii_in_query: bool = True
    allow_unlimited_calls: bool = True
    allow_external_domain_bypass: bool = True
    allow_query_without_sanitize: bool = True


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    domain_filter: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    domain: str


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    search_available: bool
    guard_passed: bool


class SearchGuardResult(BaseModel):
    allowed: bool
    blocking_flags: list[str] = Field(default_factory=list)


__all__ = [
    "SearchGuardResult",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchRuntimePolicy",
]
