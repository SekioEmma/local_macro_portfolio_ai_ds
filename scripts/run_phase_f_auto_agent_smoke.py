"""Run Phase F autonomous planned natural-answer smoke checks."""
from __future__ import annotations

import argparse
import json
import re
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
from app_backend.schemas.macro_brief import REQUIRED_BOUNDARY_KEYWORDS  # noqa: E402
from app_backend.services.agent_api_service import AgentRunService  # noqa: E402
from app_backend.services.agent_runtime import AgentRuntimeConfig  # noqa: E402
from app_backend.services.agent_tool_registry import AgentToolRegistry, ToolSpec  # noqa: E402
from app_backend.services.agent_trace_service import AgentTraceService  # noqa: E402
from app_backend.services.deepseek_real_transport import DeepSeekRealTransport  # noqa: E402
from app_backend.services.llm_provider_adapter import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    DeepSeekProviderAdapter,
)


Mode = Literal["fixture", "live"]
_NEW_YORK = ZoneInfo("America/New_York")
AUTO_SESSION_ID = "phase-f-auto-agent-smoke"
AUTO_QUESTION = (
    "请以自然中文回答：结合 SPY、QQQ、长端利率和本地宏观仪表盘，"
    "判断当前美国宏观风险状态。只做研究辅助，不给交易指令。"
)
FORBIDDEN_RESPONSE_MARKERS = (
    "market_value",
    "cost_basis",
    "account_number",
    "broker_login",
    "access_token",
    "api_key",
)


class NaturalFixtureProvider:
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
        evidence_id = _first_evidence_id(messages)
        boundary = " ".join(REQUIRED_BOUNDARY_KEYWORDS)
        return ChatResponse(
            content=(
                "结论：当前更适合按观察状态处理，而不是直接给出仓位或交易动作。"
                f" 本地证据显示 SPY 报价、QQQ 报价和 10Y 利率点已经进入证据包 [{evidence_id}]；"
                "仪表盘信息用于约束解释范围。若后续利率继续上行，成长资产的估值压力会更敏感；"
                "若利率回落且风险资产保持韧性，宏观压力会边际缓和。"
                " 本轮没有读取或输出任何持仓明细。"
                f" 边界：{boundary}。"
            )
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


def run_auto_smoke(
    *,
    mode: Mode = "fixture",
    trace_dir: Path | None = None,
) -> dict[str, Any]:
    provider = NaturalFixtureProvider() if mode == "fixture" else None
    live_call_counter = {"count": 0}
    tool_calls: list[dict[str, Any]] = []
    resolved_trace_dir = trace_dir
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if resolved_trace_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="phase_f_auto_trace_")
        resolved_trace_dir = Path(temp_dir.name)
    try:
        service = _service_for_mode(
            mode=mode,
            provider=provider,
            trace_dir=resolved_trace_dir,
            live_call_counter=live_call_counter,
            tool_calls=tool_calls,
        )
        started_at = perf_counter()
        response = service.run(
            AgentRunRequest(
                session_id=AUTO_SESSION_ID,
                user_question=AUTO_QUESTION,
                confirm_external_search=False,
                include_holdings=False,
                source_visibility_mode="public",
                output_mode="natural_answer",
            )
        )
        elapsed_seconds = perf_counter() - started_at
        provider_call_count = len(provider.calls) if provider is not None else live_call_counter["count"]
        checks = _evaluate_response(response, provider_call_count=provider_call_count, tool_calls=tool_calls)
        return {
            "mode": mode,
            "session_id": response.session_id,
            "trace_session_id": response.trace_session_id,
            "output_mode": response.output_mode,
            "final_status": response.final_status,
            "steps": response.steps,
            "provider_call_count": provider_call_count,
            "warning_codes": [warning.code for warning in response.warnings],
            "check_status": "passed" if not checks else "failed",
            "failed_checks": checks,
            "external_search_confirmed": False,
            "include_holdings": False,
            "natural_answer": response.natural_answer,
            "natural_answer_preview": response.natural_answer[:500],
            "source_markdown": response.source_markdown,
            "validation_record": _build_validation_record(
                response=response,
                mode=mode,
                provider_call_count=provider_call_count,
                tool_calls=tool_calls,
                elapsed_seconds=elapsed_seconds,
            ),
        }
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def _service_for_mode(
    *,
    mode: Mode,
    provider: NaturalFixtureProvider | None,
    trace_dir: Path,
    live_call_counter: dict[str, int],
    tool_calls: list[dict[str, Any]],
) -> AgentRunService:
    runtime_config = AgentRuntimeConfig(
        writing_max_tokens_per_call=3000,
        max_wall_clock_seconds=90,
        max_provider_call_seconds=60,
        max_tool_call_seconds=5,
        provider_max_retries=0,
    )
    provider_factory: Any
    current_date_provider: Any
    if mode == "fixture":
        if provider is None:
            raise ValueError("fixture mode requires a provider")

        def provider_factory() -> NaturalFixtureProvider:
            return provider

        def current_date_provider() -> date:
            return date(2026, 7, 2)

    else:

        def provider_factory() -> CountingProvider:
            return CountingProvider(
                DeepSeekProviderAdapter(
                    transport=DeepSeekRealTransport(
                        timeout_seconds=runtime_config.max_provider_call_seconds,
                    )
                ),
                live_call_counter,
            )

        def current_date_provider() -> date:
            return datetime.now(_NEW_YORK).date()

    return AgentRunService(
        provider_factory=provider_factory,
        registry_factory=lambda _confirm_external_search: _controlled_registry(tool_calls),
        trace_factory=lambda: AgentTraceService(root_dir=trace_dir),
        current_date_provider=current_date_provider,
        runtime_config=runtime_config,
        enabled_tool_names=["dashboard_query", "quote_etf", "treasury_curve"],
    )


def _controlled_registry(tool_calls: list[dict[str, Any]]) -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="dashboard_query",
            description="Return a deterministic macro dashboard status for F-AUTO smoke.",
            parameters_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda args: _record_call(tool_calls, "dashboard_query", args)
            or {
                "series": "macro_dashboard",
                "value": 1,
                "unit": "status",
                "overall_status": "watch",
                "observation_date": "2026-07-01",
            },
        )
    )
    registry.register(
        ToolSpec(
            name="quote_etf",
            description="Return deterministic ETF quote points for F-AUTO smoke.",
            parameters_schema={"type": "object"},
            handler=lambda args: _record_call(tool_calls, "quote_etf", args)
            or {
                "quotes": [
                    {
                        "symbol": symbol,
                        "value": 640.5 if symbol == "SPY" else 560.25,
                        "unit": "USD",
                        "status": "ok",
                        "observation_date": "2026-07-01",
                    }
                    for symbol in args.get("symbols", [])
                ]
            },
        )
    )
    registry.register(
        ToolSpec(
            name="treasury_curve",
            description="Return a deterministic Treasury curve point for F-AUTO smoke.",
            parameters_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda args: _record_call(tool_calls, "treasury_curve", args)
            or {
                "points": [
                    {
                        "tenor": "10Y",
                        "source_series": "DGS10",
                        "value": 4.35,
                        "unit": "%",
                        "observation_date": "2026-07-01",
                        "status": "ok",
                    }
                ],
                "status": "ok",
            },
        )
    )
    return registry


def _record_call(tool_calls: list[dict[str, Any]], tool_name: str, args: dict[str, Any]) -> None:
    tool_calls.append({"tool_name": tool_name, "args": dict(args)})


def _first_evidence_id(messages: list[ChatMessage]) -> str:
    text = "\n".join(message.content for message in messages)
    matches = re.findall(r"\bev_[A-Za-z0-9_]+", text)
    for item in matches:
        if item != "ev_x":
            return item
    raise RuntimeError("natural smoke did not receive evidence ids")


def _evaluate_response(
    response: AgentRunResponse,
    *,
    provider_call_count: int,
    tool_calls: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    if response.output_mode != "natural_answer":
        failures.append("output_mode_not_natural_answer")
    if response.final_status != "ok":
        failures.append("final_status_not_ok")
    if not response.natural_answer.strip():
        failures.append("natural_answer_empty")
    if response.brief is not None or response.partial_brief is not None:
        failures.append("structured_brief_unexpected")
    if response.warnings:
        failures.append("warnings_present")
    if provider_call_count != 1:
        failures.append("provider_call_count_not_one")
    planned_tools = [step.tool_name for step in response.information_plan.tool_plan.steps]
    for expected in ("dashboard_query", "quote_etf", "treasury_curve"):
        if expected not in planned_tools:
            failures.append(f"planned_tool_missing:{expected}")
    executed_tools = [item["tool_name"] for item in tool_calls]
    for expected in ("dashboard_query", "quote_etf", "treasury_curve"):
        if expected not in executed_tools:
            failures.append(f"executed_tool_missing:{expected}")
    serialized = response.model_dump_json()
    for marker in FORBIDDEN_RESPONSE_MARKERS:
        if marker in serialized:
            failures.append(f"forbidden_marker_present:{marker}")
    answer = response.natural_answer
    for keyword in REQUIRED_BOUNDARY_KEYWORDS:
        if keyword not in answer:
            failures.append(f"boundary_keyword_missing:{keyword}")
    return failures


def _build_validation_record(
    *,
    response: AgentRunResponse,
    mode: Mode,
    provider_call_count: int,
    tool_calls: list[dict[str, Any]],
    elapsed_seconds: float,
) -> dict[str, Any]:
    return {
        "run_id": response.session_id,
        "current_date": "2026-07-02" if mode == "fixture" else datetime.now(_NEW_YORK).date().isoformat(),
        "planned_tool_sequence": [
            step.tool_name for step in response.information_plan.tool_plan.steps
        ],
        "executed_tool_sequence": [item["tool_name"] for item in tool_calls],
        "tool_args": tool_calls,
        "provider_calls": provider_call_count,
        "evidence_id_count": response.natural_answer.count("ev_"),
        "warning_count": len(response.warnings),
        "include_holdings": False,
        "external_search_confirmed": False,
        "elapsed_seconds": 0.0 if mode == "fixture" else round(elapsed_seconds, 3),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase F planned natural-answer smoke.")
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--trace-dir", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    result = run_auto_smoke(mode=args.mode, trace_dir=args.trace_dir)
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
