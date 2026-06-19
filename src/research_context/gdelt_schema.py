from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PROVIDER = "gdelt_cloud"
SOURCE_BADGE = "research_context"
TRIGGER_ELIGIBILITY = "research_context_only"
INTERPRETATION_BOUNDARY = (
    "News and event intensity is aggregate research context, not probability, "
    "financial fact, market forecast, or portfolio guidance."
)


@dataclass(frozen=True)
class GdeltEventSummaryBucket:
    provider: str
    query_key: str
    window_start: str
    window_end: str
    group_by: str
    bucket_key: str
    event_count: int
    conflict_event_count: int
    cameoplus_event_count: int
    fatality_event_count: int
    fatalities: int
    article_count: int
    avg_significance: float | None
    max_significance: float | None
    avg_goldstein_scale: float | None
    avg_market_sensitivity: float | None
    avg_confidence: float | None
    raw_payload_hash: str
    ingested_at: str
    source_badge: str = SOURCE_BADGE
    trigger_eligibility: str = TRIGGER_ELIGIBILITY
    ai_context_allowed: bool = False
    interpretation_boundary: str = INTERPRETATION_BOUNDARY

    def __post_init__(self) -> None:
        _validate_common(self)
        for field in (
            "event_count",
            "conflict_event_count",
            "cameoplus_event_count",
            "fatality_event_count",
            "fatalities",
            "article_count",
        ):
            if getattr(self, field) < 0:
                raise ValueError(f"{field}_must_be_non_negative")

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GdeltStorySummaryBucket:
    provider: str
    query_key: str
    window_start: str
    window_end: str
    group_by: str
    bucket_key: str
    story_count: int
    article_count: int
    linked_event_count: int
    avg_significance: float | None
    max_significance: float | None
    avg_linked_event_market_sensitivity: float | None
    avg_linked_event_goldstein_scale: float | None
    avg_confidence: float | None
    raw_payload_hash: str
    ingested_at: str
    source_badge: str = SOURCE_BADGE
    trigger_eligibility: str = TRIGGER_ELIGIBILITY
    ai_context_allowed: bool = False
    interpretation_boundary: str = INTERPRETATION_BOUNDARY

    def __post_init__(self) -> None:
        _validate_common(self)
        for field in ("story_count", "article_count", "linked_event_count"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field}_must_be_non_negative")

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


def _validate_common(bucket: Any) -> None:
    if bucket.provider != PROVIDER:
        raise ValueError("gdelt_provider_must_be_gdelt_cloud")
    if bucket.source_badge != SOURCE_BADGE:
        raise ValueError("gdelt_source_badge_must_be_research_context")
    if bucket.trigger_eligibility != TRIGGER_ELIGIBILITY:
        raise ValueError("gdelt_trigger_must_be_research_context_only")
    if bucket.ai_context_allowed:
        raise ValueError("gdelt_ai_context_must_default_false")
    for field in (
        "query_key",
        "window_start",
        "window_end",
        "group_by",
        "bucket_key",
        "raw_payload_hash",
        "ingested_at",
    ):
        if not str(getattr(bucket, field) or "").strip():
            raise ValueError(f"{field}_is_required")
