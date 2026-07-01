"""Run the Phase F MacroBrief agent through a controlled local smoke path."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
for _path in (_REPO_ROOT, _SRC_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from app_backend.schemas.agent_api import AgentRunRequest, AgentRunResponse  # noqa: E402
from app_backend.schemas.macro_brief import REQUIRED_BOUNDARY_KEYWORDS, REQUIRED_MODULE_KEYS  # noqa: E402
from app_backend.services.agent_api_service import AgentRunService  # noqa: E402
from app_backend.services.agent_runtime import AgentRuntimeConfig  # noqa: E402
from app_backend.services.agent_tool_registry import (  # noqa: E402
    AgentToolRegistry,
    ToolSpec,
    make_finalize_macro_brief_tool,
)
from app_backend.services.agent_trace_service import AgentTraceService  # noqa: E402
from app_backend.services.deepseek_real_transport import DeepSeekRealTransport  # noqa: E402
from app_backend.services.llm_provider_adapter import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    DeepSeekProviderAdapter,
    ToolCall,
)


Mode = Literal["fixture", "live"]
_NEW_YORK = ZoneInfo("America/New_York")
CONTROLLED_SESSION_ID = "phase-f-controlled-smoke"
ACCEPTANCE_QUESTIONS = (
    "当前美国宏观环境综合评估",
    "未来三个月组合风险暴露如何理解",
    "长端利率、美元、信用利差与风险资产的当前关系",
    "Fed、通胀、就业与能源风险的传导路径",
)
CONTROLLED_QUESTION = (
    "Build a controlled Phase F MacroBrief for release verification. "
    "The acceptance question set is: 当前美国宏观环境综合评估; "
    "未来三个月组合风险暴露如何理解; "
    "长端利率、美元、信用利差与风险资产的当前关系; "
    "Fed、通胀、就业与能源风险的传导路径. "
    "First call treasury_curve. Then call finalize_macro_brief. "
    "For this smoke, use exactly one confirmed_facts item: id=f1, describing "
    "the 10Y Treasury point returned by treasury_curve. Use the registered "
    "evidence_id returned by the treasury_curve tool for f1 and for every "
    "judgment. Every judgment must have evidence_supports=[\"f1\"]. "
    "Do not add any other confirmed facts. For SPY, QQQ, SHY, and GLD "
    "market_state cards, set price=null, change_pct=null, as_of=null because "
    "quote_etf is not enabled. "
    "The final MacroBrief core_conclusion and boundary_notice must include "
    "研究辅助输出, 非自动投资决策, and 需要用户审阅."
)
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
                        id="phase-f-treasury-curve-call",
                        name="treasury_curve",
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


class CountingProvider:
    name = "deepseek"

    def __init__(self, provider: DeepSeekProviderAdapter, counter: dict[str, int]) -> None:
        self._provider = provider
        self._counter = counter

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
        self._counter["count"] = self._counter.get("count", 0) + 1
        return self._provider.chat(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            max_tokens=max_tokens,
        )


def run_controlled_smoke(
    *,
    mode: Mode = "fixture",
    trace_dir: Path | None = None,
    confirm_external_search: bool = False,
) -> dict[str, Any]:
    provider = ControlledFixtureProvider() if mode == "fixture" else None
    live_call_counter = {"count": 0}
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
            live_call_counter=live_call_counter,
        )
        runtime_events = []
        started_at = perf_counter()
        response = service.run(
            AgentRunRequest(
                session_id=CONTROLLED_SESSION_ID,
                user_question=CONTROLLED_QUESTION,
                confirm_external_search=False,
                include_holdings=False,
                source_visibility_mode="public",
            ),
            event_callback=runtime_events.append,
        )
        elapsed_seconds = perf_counter() - started_at
        provider_call_count = len(provider.calls) if provider is not None else live_call_counter["count"]
        checks = _evaluate_response(response, provider_call_count=provider_call_count)
        validation_record = _build_validation_record(
            response=response,
            runtime_events=runtime_events,
            mode=mode,
            provider_call_count=provider_call_count,
            confirm_external_search=False,
            elapsed_seconds=elapsed_seconds,
        )
        return {
            "mode": mode,
            "session_id": response.session_id,
            "trace_session_id": response.trace_session_id,
            "final_status": response.final_status,
            "steps": response.steps,
            "provider_call_count": provider_call_count,
            "warning_codes": [warning.code for warning in response.warnings],
            "check_status": "passed" if not checks else "failed",
            "failed_checks": checks,
            "external_search_confirmed": False,
            "include_holdings": False,
            "validation_record": validation_record,
        }
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def _service_for_mode(
    *,
    mode: Mode,
    provider: ControlledFixtureProvider | None,
    trace_dir: Path,
    live_call_counter: dict[str, int],
) -> AgentRunService:
    runtime_config = AgentRuntimeConfig(
        research_max_steps=2,
        writing_max_steps=2,
        max_wall_clock_seconds=90,
        max_provider_call_seconds=60,
        max_tool_call_seconds=5,
        provider_max_retries=0,
    )
    if mode == "fixture":
        if provider is None:
            raise ValueError("fixture mode requires a controlled fixture provider")
        return AgentRunService(
            provider_factory=lambda: provider,
            registry_factory=lambda _confirm_external_search: _controlled_registry(),
            trace_factory=lambda: AgentTraceService(root_dir=trace_dir),
            current_date_provider=lambda: date(2026, 6, 30),
            runtime_config=runtime_config,
            enabled_tool_names=["treasury_curve", "finalize_macro_brief"],
        )
    return AgentRunService(
        provider_factory=lambda: CountingProvider(
            DeepSeekProviderAdapter(
                transport=DeepSeekRealTransport(
                    timeout_seconds=runtime_config.max_provider_call_seconds,
                )
            ),
            live_call_counter,
        ),
        registry_factory=lambda _confirm_external_search: _controlled_registry(),
        trace_factory=lambda: AgentTraceService(root_dir=trace_dir),
        current_date_provider=lambda: datetime.now(_NEW_YORK).date(),
        runtime_config=runtime_config,
        enabled_tool_names=["treasury_curve", "finalize_macro_brief"],
    )


def _controlled_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="treasury_curve",
            description="Return a deterministic local Treasury curve point for Phase F release smoke.",
            parameters_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda _args: {
                "points": [
                    {
                        "tenor": "10Y",
                        "source_series": "DGS10",
                        "value": 4.3,
                        "observation_date": "2026-06-29",
                        "status": "ok",
                    }
                ],
                "status": "ok",
                "mode": "controlled_fixture",
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


def _evaluate_response(response: AgentRunResponse, *, provider_call_count: int | None) -> list[str]:
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
    if provider_call_count is not None and provider_call_count < 2:
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


def _build_validation_record(
    *,
    response: AgentRunResponse,
    runtime_events: list[Any],
    mode: Mode,
    provider_call_count: int | None,
    confirm_external_search: bool,
    elapsed_seconds: float,
) -> dict[str, Any]:
    brief = response.brief or {}
    tool_call_sequence = _tool_call_sequence(runtime_events)
    return {
        "run_id": response.session_id,
        "current_date": _current_date_for_mode(mode),
        "acceptance_questions": list(ACCEPTANCE_QUESTIONS),
        "cutoffs": _cutoffs_from_brief(brief),
        "tool_call_sequence": tool_call_sequence,
        "evidence_count": _evidence_counts_from_events(runtime_events)["total"],
        "evidence_counts": _evidence_counts_from_events(runtime_events),
        "unavailable_modules": _unavailable_modules(brief),
        "asynchronous_inputs": brief.get("asynchronous_inputs") if brief else None,
        "final_status": response.final_status,
        "budget_usage": {
            "steps": response.steps,
            "provider_calls": provider_call_count,
            "tool_calls": len(tool_call_sequence),
            "warning_count": len(response.warnings),
            "include_holdings": False,
            "external_search_confirmed": confirm_external_search,
        },
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def _current_date_for_mode(mode: Mode) -> str:
    if mode == "fixture":
        return "2026-06-30"
    return datetime.now(_NEW_YORK).date().isoformat()


def _cutoffs_from_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_generated_at": brief.get("report_generated_at"),
        "market_data_cutoff": brief.get("market_data_cutoff"),
        "policy_data_cutoff": brief.get("policy_data_cutoff"),
        "macro_data_cutoff": brief.get("macro_data_cutoff"),
        "public_news_cutoff": brief.get("public_news_cutoff"),
        "max_market_data_age_trading_days": brief.get("max_market_data_age_trading_days"),
    }


def _tool_call_sequence(runtime_events: list[Any]) -> list[str]:
    sequence: list[str] = []
    for event in runtime_events:
        if getattr(event, "type", None) != "llm_completion":
            continue
        tool_calls = event.data.get("tool_calls") if isinstance(event.data, dict) else None
        if isinstance(tool_calls, list):
            sequence.extend(item for item in tool_calls if isinstance(item, str))
    return sequence


def _evidence_counts_from_events(runtime_events: list[Any]) -> dict[str, int]:
    counts = {
        "total": 0,
        "official": 0,
        "public": 0,
        "institutional": 0,
        "local_data_foundation": 0,
        "licensed_manual_data": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    for event in runtime_events:
        if getattr(event, "type", None) != "tool_result" or not isinstance(event.data, dict):
            continue
        evidence_ids = event.data.get("evidence_ids")
        evidence_id_count = len(evidence_ids) if isinstance(evidence_ids, list) else 0
        tier_counts = event.data.get("evidence_tier_counts")
        if not isinstance(tier_counts, dict):
            counts["unknown"] += evidence_id_count
            counts["total"] += evidence_id_count
            continue
        tier_total = 0
        for tier, raw_count in tier_counts.items():
            if not isinstance(raw_count, int):
                continue
            key = _evidence_count_key(str(tier))
            counts[key] += raw_count
            tier_total += raw_count
        counts["total"] += tier_total
    return counts


def _evidence_count_key(tier: str) -> str:
    if tier == "official_evidence":
        return "official"
    if tier == "public_reporting":
        return "public"
    if tier == "institutional_view":
        return "institutional"
    if tier in {"local_data_foundation", "licensed_manual_data", "unavailable"}:
        return tier
    return "unknown"


def _unavailable_modules(brief: dict[str, Any]) -> list[str]:
    unavailable: list[str] = []
    for fact in brief.get("confirmed_facts") or []:
        if isinstance(fact, dict) and fact.get("claim_status") == "unavailable":
            unavailable.append(f"fact:{fact.get('id') or 'unknown'}")
    for card in brief.get("market_state") or []:
        if not isinstance(card, dict):
            continue
        if card.get("price") is None or card.get("change_pct") is None:
            unavailable.append(f"market_state:{card.get('symbol') or 'unknown'}")
    return unavailable


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a controlled Phase F MacroBrief agent smoke.")
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--trace-dir", type=Path, default=None)
    parser.add_argument("--confirm-external-search", action="store_true")
    parser.add_argument("--report-path", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    result = run_controlled_smoke(
        mode=args.mode,
        trace_dir=args.trace_dir,
        confirm_external_search=args.confirm_external_search,
    )
    if args.report_path is not None:
        _write_report(args.report_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["check_status"] == "passed" else 1


def _write_report(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
