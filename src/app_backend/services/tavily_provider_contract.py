from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.search_external import SearchRequest


class TavilyProviderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    max_results: int
    include_domains: list[str] = Field(default_factory=list)


def build_tavily_provider_payload(
    request: SearchRequest,
) -> TavilyProviderPayload:
    return TavilyProviderPayload(
        query=request.query,
        max_results=request.max_results,
        include_domains=list(request.domain_filter),
    )


__all__ = [
    "TavilyProviderPayload",
    "build_tavily_provider_payload",
]
