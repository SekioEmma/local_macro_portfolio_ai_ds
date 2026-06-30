"""Run the Phase F MacroBrief agent through a controlled local smoke path."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
for _path in (_REPO_ROOT, _SRC_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from app_backend.schemas.agent_api import AgentRunRequest, AgentRunResponse  # noqa: E402
from app_backend.schemas.macro_brief import REQUIRED_BOUNDARY_KEYWORDS, REQUIRED_MODULE_KEYS  # noqa: E402
from app_backend.services.agent_api_service import AgentRunService, build_default_agent_run_service  # noqa: E402
from app_backend.services.agent_runtime import AgentRuntimeConfig  # noqa: E402
from app_backend.services.agent_tool_registry import (  # noqa: E402
    AgentToolRegistry,
    ToolSpec,
    make_finalize_macro_brief_tool,
)
from app_backend.services.agent_trace_service import AgentTraceService  # noqa: E402
from app_backend.services.llm_provider_adapter import ChatMessage, ChatResponse, ToolCall  # noqa: E402


Mode = Literal["fixture", "live"]
CONTROLLED_SESSION_ID = "phase-f-controlled-smoke"
CONTROLLED_QUESTION = "Build a controlled Phase F MacroBrief for release verification."
FORBIDDEN_RESPONSE_MARKERS = (
    "market_value_usd",
    "cost_basis",
    "account_number",
    "broker_login",
    "access_token",
    "api_key",
)
REQUIRED_STATUS_MARKERS = (
    "研究辅助输出",
    "非自动投资决策",
    "需要用户审阅",
)


class ControlledFixtureProvider:
    name = "deepseek"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 4000,
    ) -> ChatResponse:
        self.calls.append(
            {
                "model": model,
                "messages": list(messages),
                "tools": list(tools or []),
                "tool_choice": tool_choice,
                "response_format": response_format,
                "max_tokens": max_tokens,
            }
        )
        if len(self.calls) == 1:
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="phase-f-dashboard-call",
                        name="dashboard_query",
                        arguments={},
                    )
                ],
                finish_reason="tool_calls",
            )
        evidence_id = _latest_registered_evidence_id(messages)
        return ChatResponse(
            tool_calls=[
                ToolCall(
                    id="phase-f-finalize-call",
                    name="finalize_macro_brief",
                    arguments={"brief": _controlled_brief_payload(evidence_id)},
                )
            ],
            finish_reason="tool_calls",
        )


def run_controlled_smoke(
    *,
    mode: Mode = "fixture",
    trace_dir: Path | None = None,
    confirm_external_search: bool = False,
) -> dict[str, Any]:
    provider = ControlledFixtureProvider()
    resolved_trace_dir = trace_dir
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if resolved_trace_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="phase_f_controlled_trace_")
        resolved_trace_dir = Path(temp_dir.name)
    try:
        service = _service_for_mode(
            mode=mode,
            provider=provider,
            trace_dir=resolved_trace_dir,
        )
        response = service.run(
            AgentRunRequest(
                session_id=CONTROLLED_SESSION_ID,
                user_question=CONTROLLED_QUESTION,
                confirm_external_search=confirm_external_search if mode == "live" else False,
                include_holdings=False,
                source_visibility_mode="public",
            )
        )
        checks = _evaluate_response(response, provider_call_count=len(provider.calls))
        return {
            "mode": mode,
            "session_id": response.session_id,
            "trace_session_id": response.trace_session_id,
            "final_status": response.final_status,
            "steps": response.steps,
            "provider_call_count": len(provider.calls),
            "warning_codes": [warning.code for warning in response.warnings],
            "check_status": "passed" if not checks else "failed",
            "failed_checks": checks,
            "external_search_confirmed": confirm_external_search if mode == "live" else False,
            "include_holdings": False,
        }
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def _service_for_mode(
    *,
    mode: Mode,
    provider: ControlledFixtureProvider,
    trace_dir: Path,
) -> AgentRunService:
    if mode == "fixture":
        return AgentRunService(
            provider_factory=lambda: provider,
            registry_factory=lambda _confirm_external_search: _controlled_registry(),
            trace_factory=lambda: AgentTraceService(root_dir=trace_dir),
            current_date_provider=lambda: date(2026, 6, 30),
            runtime_config=AgentRuntimeConfig(
                research_max_steps=2,
                writing_max_steps=2,
                max_wall_clock_seconds=30,
                max_provider_call_seconds=15,
                max_tool_call_seconds=5,
                provider_max_retries=0,
            ),
        )
    return build_default_agent_run_service()


def _controlled_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="dashboard_query",
            description="Return a deterministic local dashboard summary for Phase F release smoke.",
            parameters_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda _args: {
                "series": "DGS10",
                "value": 4.3,
                "unit": "%",
                "as_of": "2026-06-29",
                "overall_status": "controlled_fixture",
            },
        )
    )
    registry.register(make_finalize_macro_brief_tool())
    return registry


def _latest_registered_evidence_id(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role != "tool":
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        content = payload.get("content") if isinstance(payload, dict) else None
        ids = content.get("registered_evidence_ids") if isinstance(content, dict) else None
        if isinstance(ids, list):
            for item in ids:
                if isinstance(item, str) and item:
                    return item
    raise RuntimeError("controlled smoke did not receive registered evidence")


def _controlled_brief_payload(evidence_id: str) -> dict[str, Any]:
    source_id = "placeholder_source_projected_from_ledger"
    return {
        "core_conclusion": (
            "研究辅助输出：本次 controlled smoke 显示宏观环境仍处于观察状态；"
            "非自动投资决策，需要用户审阅后才能进入任何人工决策流程。"
        ),
        "market_state": [
            {"symbol": symbol, "price": 400.0, "change_pct": 0.1, "as_of": "2026-06-29"}
            for symbol in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": [
            {
                "id": "f1",
                "statement": "Controlled dashboard fixture reported DGS10 at 4.3.",
                "value": 4.3,
                "unit": "%",
                "source_id": source_id,
                "evidence_ids": [evidence_id],
                "claim_status": "observed",
                "as_of": "2026-06-29",
            }
        ],
        "judgments": [
            {
                "claim": "Rate pressure remains the primary watch item in this controlled run.",
                "evidence_supports": ["f1"],
                "evidence_ids": [evidence_id],
                "claim_type": "direct_evidence",
                "temporal_scope": "current_run",
            }
        ],
        "module_table": [
            {
                "module_key": key,
                "module_name_zh": key,
                "status": "watch",
                "note": "Controlled smoke fixture; not a live market assessment.",
            }
            for key in REQUIRED_MODULE_KEYS
        ],
        "risk_assessment": {
            "current_label": "watch",
            "summary": "Controlled fixture only; production release still requires human checklist review.",
            "upgrade_triggers": ["Credit spreads or funding pressure worsen in validated data."],
            "downgrade_triggers": ["Validated inflation and yield pressure cool together."],
        },
        "forward_indicators": [
            {
                "name": f"controlled_indicator_{index}",
                "release_date": "2026-07-10",
                "relevance": "Release checklist placeholder for controlled smoke.",
            }
            for index in range(1, 6)
        ],
        "scenarios": {
            "base": {
                "trigger_conditions": ["Growth slows gradually."],
                "transmission_path": "Yields stabilize while risk assets consolidate.",
                "note": "Controlled fixture.",
            },
            "bullish": {
                "trigger_conditions": ["Inflation cools faster than expected."],
                "transmission_path": "Real-yield pressure eases.",
                "note": "Controlled fixture.",
            },
            "bearish": {
                "trigger_conditions": ["Inflation or funding stress reaccelerates."],
                "transmission_path": "Rate pressure tightens financial conditions.",
                "note": "Controlled fixture.",
            },
            "systemic": {
                "trigger_conditions": ["Credit or liquidity stress gaps wider."],
                "transmission_path": "Funding stress spills into risk assets.",
                "note": "Controlled fixture.",
            },
        },
        "source_list": [
            {
                "id": source_id,
                "title": "Controlled dashboard fixture",
                "accessed_at": "2026-06-30T00:00:00Z",
            }
        ],
        "boundary_notice": " ".join(
            (
                "研究辅助输出",
                "非自动投资决策",
                "需要用户审阅",
                *REQUIRED_BOUNDARY_KEYWORDS,
            )
        ),
    }


def _evaluate_response(response: AgentRunResponse, *, provider_call_count: int) -> list[str]:
    failures: list[str] = []
    if response.final_status != "ok":
        failures.append("final_status_not_ok")
    if response.brief is None:
        failures.append("brief_missing")
    if response.warnings:
        failures.append("warnings_present")
    if response.source_visibility_mode != "public":
        failures.append("source_visibility_not_public")
    if response.steps < 2:
        failures.append("agent_steps_below_controlled_minimum")
    if provider_call_count < 2:
        failures.append("provider_calls_below_controlled_minimum")
    serialized = response.model_dump_json()
    for marker in FORBIDDEN_RESPONSE_MARKERS:
        if marker in serialized:
            failures.append(f"forbidden_marker_present:{marker}")
    rendered = response.rendered_markdown
    for marker in REQUIRED_STATUS_MARKERS:
        if marker not in rendered:
            failures.append(f"required_status_marker_missing:{marker}")
    return failures


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a controlled Phase F MacroBrief agent smoke.")
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--trace-dir", type=Path, default=None)
    parser.add_argument("--confirm-external-search", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    result = run_controlled_smoke(
        mode=args.mode,
        trace_dir=args.trace_dir,
        confirm_external_search=args.confirm_external_search,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["check_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
