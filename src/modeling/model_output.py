from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelOutput:
    model_key: str
    module_key: str
    metric_key: str
    value: float | str | bool | None
    value_text: str
    status: str
    source_badge: str
    freshness_status: str
    interpretation_boundary: str
    component_contributions: dict[str, Any] | None = None
    ai_context_allowed: bool = True

    def to_metric_payload(
        self,
        *,
        display_name: str | None = None,
        unit: str | None = None,
        source: str = "local_rules",
        source_series: str | None = None,
        observation_date: str | None = None,
        generated_at: str | None = None,
        missing_reason: str | None = None,
        input_evidence: list[dict[str, Any]] | None = None,
        missing_inputs: list[str] | None = None,
        ai_context_tier: str = "model_output",
        trigger_eligibility: str = "reference_review_only",
    ) -> dict[str, Any]:
        return {
            "metric_key": self.metric_key,
            "display_name": display_name or self.metric_key.replace("_", " "),
            "value": self.value,
            "value_text": self.value_text,
            "unit": unit,
            "status": self.status,
            "source": source,
            "source_badge": self.source_badge,
            "source_series": source_series,
            "observation_date": observation_date,
            "generated_at": generated_at,
            "freshness_status": self.freshness_status,
            "missing_reason": missing_reason,
            "interpretation_hint": self.interpretation_boundary,
            "interpretation_boundary": self.interpretation_boundary,
            "ai_context_allowed": self.ai_context_allowed,
            "input_evidence": input_evidence,
            "component_contributions": self.component_contributions,
            "missing_inputs": missing_inputs,
            "ai_context_tier": ai_context_tier,
            "trigger_eligibility": trigger_eligibility,
        }
