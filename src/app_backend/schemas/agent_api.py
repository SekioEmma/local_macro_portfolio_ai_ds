"""API schemas for Phase F7 MacroBrief agent endpoints."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.agent_information_plan import AgentInformationPlan
from app_backend.services.agent_runtime import FinalStatus
from app_backend.services.macro_brief_sources import (
    MacroBriefSourceReference,
    SourceVisibilityMode,
)


AgentApiStatus = FinalStatus | Literal["unavailable"]


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    include_holdings: bool = False
    holdings_consent_token: str | None = Field(default=None, min_length=16, max_length=256)
    confirm_external_search: bool = False
    source_visibility_mode: SourceVisibilityMode = "public"


class HoldingsConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    confirm_holdings_external_context: bool = False


class HoldingsConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    holdings_consent_token: str
    expires_at: str
    ttl_seconds: int


class AgentApiWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str = ""


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    final_status: AgentApiStatus
    trace_session_id: str
    source_visibility_mode: SourceVisibilityMode
    brief: dict[str, Any] | None = None
    partial_brief: dict[str, Any] | None = None
    rendered_markdown: str = ""
    source_markdown: str = ""
    sources: list[MacroBriefSourceReference] = Field(default_factory=list)
    information_plan: AgentInformationPlan
    warnings: list[AgentApiWarning] = Field(default_factory=list)
    search_required: bool = False
    missing_topics: list[str] = Field(default_factory=list)
    steps: int = 0


class AgentTraceDebugResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    event_count: int
    sensitive_findings: list[str]
    message_history: list[dict[str, str]]
    events: list[dict[str, Any]]


class AgentCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    cancelled: bool
    already_cancelled: bool = False


__all__ = [
    "AgentCancelResponse",
    "AgentApiStatus",
    "AgentApiWarning",
    "AgentRunRequest",
    "AgentRunResponse",
    "AgentTraceDebugResponse",
    "HoldingsConsentRequest",
    "HoldingsConsentResponse",
]
