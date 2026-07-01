from __future__ import annotations

import json
from datetime import date
from typing import Any

from app_backend.schemas.macro_brief import REQUIRED_BOUNDARY_KEYWORDS, REQUIRED_MODULE_KEYS
from app_backend.services.agent_runtime import AgentBudget, AgentRuntimeConfig, run_agent
from app_backend.services.agent_tool_registry import (
    FINALIZE_TOOL_NAME,
    AgentToolRegistry,
    ToolSpec,
    make_finalize_macro_brief_tool,
)
from app_backend.services.llm_provider_adapter import (
    ChatMessage,
    ChatResponse,
    ProviderChatError,
    ToolCall,
)
from app_backend.services.holdings_output_guard import DISCLOSURE_WARNING_CODE
from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
)


class MockProvider:
    name = "deepseek"

    def __init__(self, responses: list[ChatResponse | Exception]) -> None:
        self.responses = responses
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
        if not self.responses:
            return ChatResponse(content="no more mocked responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClock:
    def __init__(self, *values: float) -> None:
        self._values = list(values)
        self._last = values[-1] if values else 0.0

    def __call__(self) -> float:
        if self._values:
            self._last = self._values.pop(0)
        return self._last


class EvidenceAwareProvider:
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
                    ToolCall(id="curve-call", name="treasury_curve", arguments={})
                ],
                finish_reason="tool_calls",
            )
        evidence_id = _registered_evidence_id(messages)
        payload = brief_payload()
        payload["confirmed_facts"] = payload["confirmed_facts"][:1]
        payload["confirmed_facts"][0]["as_of"] = "2026-06-29"
        for fact in payload["confirmed_facts"]:
            fact["evidence_ids"] = [evidence_id]
        payload["judgments"][0]["evidence_ids"] = [evidence_id]
        return ChatResponse(
            tool_calls=[finalize_call("final-with-auto-evidence", payload)],
            finish_reason="tool_calls",
        )


def _registered_evidence_id(messages: list[ChatMessage]) -> str:
    for message in messages:
        if message.role != "tool":
            continue
        payload = json.loads(message.content)
        ids = payload.get("content", {}).get("registered_evidence_ids") or []
        if ids:
            return ids[0]
    raise AssertionError("registered evidence id not found in tool messages")


def brief_payload() -> dict[str, Any]:
    return {
        "core_conclusion": "Macro environment remains balanced.",
        "market_state": [
            {"symbol": symbol, "price": 400.0, "change_pct": 0.1, "as_of": "2026-06-28"}
            for symbol in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": [
            {
                "id": "f1",
                "statement": "DGS10 remained elevated.",
                "value": 4.3,
                "unit": "%",
                "source_id": "s1",
                "evidence_ids": ["ev_dgs10"],
                "as_of": "2026-06-27",
            },
            {
                "id": "f2",
                "statement": "HY OAS stayed inside a watch range.",
                "value": 3.1,
                "unit": "%",
                "source_id": "s2",
                "evidence_ids": ["ev_credit"],
                "claim_status": "reported",
                "as_of": "2026-06-27",
            },
        ],
        "judgments": [
            {
                "claim": "Rate pressure is still the main transmission channel.",
                "evidence_supports": ["f1"],
                "evidence_ids": ["ev_dgs10"],
                "temporal_scope": "current_run",
            }
        ],
        "module_table": [
            {"module_key": key, "module_name_zh": key, "status": "watch", "note": None}
            for key in REQUIRED_MODULE_KEYS
        ],
        "risk_assessment": {
            "current_label": "watch",
            "summary": "Risks are balanced but data-sensitive.",
            "upgrade_triggers": ["HY OAS widens materially"],
            "downgrade_triggers": ["Inflation and yields cool together"],
        },
        "forward_indicators": [
            {"name": f"indicator_{idx}", "release_date": "2026-07-11", "relevance": "next data point"}
            for idx in range(5)
        ],
        "scenarios": {
            "base": {
                "trigger_conditions": ["growth slows gradually"],
                "transmission_path": "yields stabilize and equities consolidate",
                "note": None,
            },
            "bullish": {
                "trigger_conditions": ["inflation cools faster"],
                "transmission_path": "real yields ease and duration recovers",
                "note": None,
            },
            "bearish": {
                "trigger_conditions": ["inflation reaccelerates"],
                "transmission_path": "rate pressure tightens financial conditions",
                "note": None,
            },
            "systemic": {
                "trigger_conditions": ["credit spreads gap wider"],
                "transmission_path": "funding stress spills into risk assets",
                "note": None,
            },
        },
        "source_list": [
            {"id": "s1", "url": "https://fred.stlouisfed.org/series/DGS10", "accessed_at": "2026-06-29"},
            {"id": "s2", "rag_doc_id": "credit_snapshot", "accessed_at": "2026-06-29"},
        ],
        "boundary_notice": " ".join(REQUIRED_BOUNDARY_KEYWORDS),
    }


def make_registry(*, on_dashboard: list[dict[str, Any]] | None = None) -> AgentToolRegistry:
    registry = AgentToolRegistry()

    def dashboard_handler(args: dict[str, Any]) -> dict[str, Any]:
        if on_dashboard is not None:
            on_dashboard.append(args)
        return {"series": "DGS10", "value": 4.3}

    registry.register(
        ToolSpec(
            name="dashboard_query",
            description="Mock dashboard query.",
            parameters_schema={
                "type": "object",
                "properties": {"series": {"type": "string"}},
                "required": ["series"],
                "additionalProperties": False,
            },
            handler=dashboard_handler,
        )
    )
    registry.register(make_finalize_macro_brief_tool())
    return registry


def make_curve_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="treasury_curve",
            description="Mock treasury curve.",
            parameters_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda args: {
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
            },
        )
    )
    registry.register(make_finalize_macro_brief_tool())
    return registry


def finalize_call(call_id: str = "final", payload: dict[str, Any] | None = None) -> ToolCall:
    return ToolCall(
        id=call_id,
        name=FINALIZE_TOOL_NAME,
        arguments={"brief": payload or brief_payload()},
    )


def tool_names_from_call(call: dict[str, Any]) -> list[str]:
    return [tool["function"]["name"] for tool in call["tools"]]


def _evidence_record(
    evidence_id: str,
    *,
    tool_name: str = "treasury_curve",
    observation_date: str = "2026-06-27",
    value: float = 4.3,
    unit: str | None = "%",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="ledger-run",
        tool_name=tool_name,
        source_kind="official_primary",
        evidence_tier="official_evidence",
        title=f"Evidence {evidence_id}",
        observation_date=observation_date,
        release_date=observation_date,
        accessed_at="2026-06-30T12:00:00+00:00",
        temporal_status="observed",
        atomic_observations=(
            AtomicObservation(value=value, unit=unit, as_of=observation_date, series_id=evidence_id),
        ),
    )


def _ledger(*records: EvidenceRecord) -> RunEvidenceLedger:
    ledger = RunEvidenceLedger(run_id="ledger-run")
    for record in records:
        ledger = ledger.add(record)
    return ledger


def test_run_agent_dispatches_tool_then_finalizes():
    dispatches: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    )
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s1",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dispatches),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert result.brief is not None
    assert result.steps == 2
    assert dispatches == [{"series": "DGS10"}]
    second_call_messages = provider.calls[1]["messages"]
    assistant_tool_call = next(
        message for message in second_call_messages if message.role == "assistant"
    )
    assert assistant_tool_call.tool_calls == [
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "dashboard_query",
                "arguments": '{"series": "DGS10"}',
            },
        }
    ]
    assert any(message.role == "tool" and "DGS10" in message.content for message in second_call_messages)


def test_run_agent_cancelled_before_provider_call_makes_no_provider_request():
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])

    result = run_agent(
        session_id="cancel-before-provider",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        cancellation_requested=lambda: True,
    )

    assert result.final_status == "cancelled"
    assert result.steps == 0
    assert provider.calls == []
    assert any(warning.code == "agent_cancelled" for warning in result.warnings)
    assert result.events[-1].type == "run_cancelled"


def test_run_agent_cancelled_after_provider_call_skips_tool_dispatch():
    dispatches: list[dict[str, Any]] = []
    checks = 0
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    )
                ],
                finish_reason="tool_calls",
            )
        ]
    )

    def cancel_after_provider() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    result = run_agent(
        session_id="cancel-after-provider",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dispatches),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        cancellation_requested=cancel_after_provider,
    )

    assert result.final_status == "cancelled"
    assert result.steps == 1
    assert len(provider.calls) == 1
    assert dispatches == []
    assert not any(event.type == "tool_result" for event in result.events)


def test_run_agent_wall_clock_timeout_before_provider_call_makes_no_provider_request():
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])

    result = run_agent(
        session_id="wall-timeout-before-provider",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(max_wall_clock_seconds=1),
        monotonic_clock=FakeClock(0, 2),
    )

    assert result.final_status == "incomplete"
    assert result.steps == 0
    assert provider.calls == []
    assert any(warning.code == "timeout:wall_clock" for warning in result.warnings)
    assert result.events[-1].type == "runtime_timeout"
    assert result.events[-1].data["kind"] == "wall_clock"


def test_run_agent_provider_timeout_returns_incomplete_after_provider_call():
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])

    result = run_agent(
        session_id="provider-timeout",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(max_provider_call_seconds=1),
        monotonic_clock=FakeClock(0, 0, 0, 2),
    )

    assert result.final_status == "incomplete"
    assert result.steps == 1
    assert len(provider.calls) == 1
    assert any(warning.code == "timeout:provider_call" for warning in result.warnings)
    assert result.events[-1].type == "runtime_timeout"
    assert result.events[-1].data["kind"] == "provider_call"


def test_run_agent_tool_timeout_appends_sanitized_tool_message_and_continues():
    dispatches: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    )
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="tool-timeout",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dispatches),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(max_tool_call_seconds=1),
        monotonic_clock=FakeClock(0, 0, 0, 0, 0, 0, 0, 2),
    )

    assert result.final_status == "ok"
    assert dispatches == [{"series": "DGS10"}]
    assert any(warning.code == "timeout:tool_call" for warning in result.warnings)
    assert any(event.type == "tool_timeout" for event in result.events)
    timeout_result = next(
        event
        for event in result.events
        if event.type == "tool_result" and event.data.get("error_code") == "tool_timeout"
    )
    assert timeout_result.data["status"] == "error"


def test_run_agent_plain_text_adds_finalize_convergence_message():
    provider = MockProvider(
        [
            ChatResponse(content="Here is a prose answer."),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s2",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert any(warning.code == "plain_text_without_tool_calls" for warning in result.warnings)
    assert any(FINALIZE_TOOL_NAME in message.content for message in provider.calls[1]["messages"] if message.role == "user")


def test_run_agent_returns_incomplete_when_finalize_never_arrives():
    provider = MockProvider([ChatResponse(content="still thinking"), ChatResponse(content="still prose")])

    result = run_agent(
        session_id="s3",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        budget=AgentBudget(max_steps=2),
    )

    assert result.final_status == "incomplete"
    assert result.brief is None
    assert result.steps == 2
    assert any(warning.code == "agent_incomplete" for warning in result.warnings)


def test_run_agent_degrades_provider_error_to_incomplete_result():
    class FailingProvider:
        name = "deepseek"

        def chat(self, **kwargs):  # noqa: ANN003, ANN201
            raise RuntimeError("provider exploded")

    result = run_agent(
        session_id="provider-error",
        user_question="Build a macro brief.",
        provider=FailingProvider(),
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "incomplete"
    assert any(warning.code == "provider_error" for warning in result.warnings)
    assert any(event.type == "provider_error" for event in result.events)


def test_run_agent_retries_retryable_provider_errors_then_succeeds():
    provider = MockProvider(
        [
            ProviderChatError("timeout"),
            ProviderChatError("server_error"),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="provider-retry",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(provider_retry_backoff_seconds=0),
        sleep_fn=lambda _: None,
    )

    retry_events = [event for event in result.events if event.type == "provider_retry"]

    assert result.final_status == "ok"
    assert len(provider.calls) == 3
    assert [event.data["error_kind"] for event in retry_events] == ["timeout", "server_error"]
    assert retry_events[0].data["next_attempt"] == 2
    assert not any(event.type == "provider_error" for event in result.events)


def test_run_agent_provider_retry_stops_when_wall_clock_deadline_expires():
    provider = MockProvider(
        [
            ProviderChatError("timeout"),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="provider-retry-deadline",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(
            max_wall_clock_seconds=5,
            provider_retry_backoff_seconds=0,
        ),
        monotonic_clock=FakeClock(0, 0, 0, 1, 10),
        sleep_fn=lambda _: None,
    )

    assert result.final_status == "incomplete"
    assert len(provider.calls) == 1
    assert any(event.type == "provider_retry" for event in result.events)
    assert result.events[-1].type == "runtime_timeout"
    assert result.events[-1].data["kind"] == "wall_clock"


def test_run_agent_does_not_retry_client_provider_error():
    provider = MockProvider([ProviderChatError("client_error")])

    result = run_agent(
        session_id="provider-client-error",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        sleep_fn=lambda _: None,
    )

    assert result.final_status == "incomplete"
    assert len(provider.calls) == 1
    assert not any(event.type == "provider_retry" for event in result.events)
    provider_error = next(event for event in result.events if event.type == "provider_error")
    assert provider_error.data["error_kind"] == "client_error"
    assert provider_error.data["retryable"] is False


def test_run_agent_missing_provider_key_returns_unavailable_without_retry():
    provider = MockProvider([ProviderChatError("missing_key")])

    result = run_agent(
        session_id="provider-missing-key",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        sleep_fn=lambda _: None,
    )

    assert result.final_status == "unavailable"
    assert len(provider.calls) == 1
    provider_error = next(event for event in result.events if event.type == "provider_error")
    assert provider_error.data["error_kind"] == "missing_key"
    assert not any(event.type == "provider_retry" for event in result.events)


def test_finalize_validation_failure_retries_once_then_succeeds():
    invalid_payload = brief_payload()
    del invalid_payload["source_list"]
    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-final", invalid_payload)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("good-final")], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s4",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert any(warning.code == "validation_retry" for warning in result.warnings)
    assert any(
        message.role == "tool"
        and message.tool_call_id == "bad-final"
        and "macro_brief_validation_failed" in message.content
        for message in provider.calls[1]["messages"]
    )
    correction_messages = [
        message.content
        for message in provider.calls[1]["messages"]
        if message.role == "user" and "macro_brief_validation_error" in message.content
    ]
    assert correction_messages
    assert "source_list" in correction_messages[0]
    assert FINALIZE_TOOL_NAME in correction_messages[0]


def test_finalize_validation_failure_twice_returns_partial_brief():
    first_invalid = brief_payload()
    del first_invalid["source_list"]
    second_invalid = brief_payload()
    second_invalid["forward_indicators"] = second_invalid["forward_indicators"][:2]

    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-final-1", first_invalid)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("bad-final-2", second_invalid)], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s5",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "validation_failed"
    assert result.brief is None
    assert result.partial_brief == second_invalid
    assert result.validation_findings is not None
    assert any("forward_indicators" in finding for finding in result.validation_findings["findings"])
    assert any(warning.code == "validation_failed" for warning in result.warnings)


def test_finalize_blocks_holdings_output_disclosure_without_partial_brief():
    leaking_payload = brief_payload()
    leaking_payload["core_conclusion"] = "Macro Sleeve has SPY market value 182247."
    provider = MockProvider(
        [ChatResponse(tool_calls=[finalize_call("leaking-final", leaking_payload)], finish_reason="tool_calls")]
    )

    result = run_agent(
        session_id="holdings-disclosure",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        include_holdings=True,
        holdings_snapshot={
            "account_name": "Macro Sleeve",
            "positions": [
                {
                    "ticker": "SPY",
                    "quantity": 250,
                    "average_cost": 420.5,
                    "market_value": 182247,
                }
            ],
        },
    )

    assert result.final_status == "validation_failed"
    assert result.brief is None
    assert result.partial_brief is None
    assert result.validation_findings is not None
    assert "account_name" in result.validation_findings["findings"]
    assert "positions[0].market_value" in result.validation_findings["findings"]
    assert any(warning.code == DISCLOSURE_WARNING_CODE for warning in result.warnings)


def test_finalize_claim_evidence_gate_retries_when_ledger_ids_are_unknown():
    fixed_payload = brief_payload()
    fixed_payload["confirmed_facts"][1]["evidence_ids"] = ["ev_known_credit"]
    fixed_payload["judgments"][0]["evidence_ids"] = ["ev_dgs10"]
    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-evidence")], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("good-evidence", fixed_payload)], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="evidence-gate",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        evidence_ledger=_ledger(
            _evidence_record("ev_dgs10"),
            _evidence_record("ev_known_credit", tool_name="rag_retrieve", value=3.1),
        ),
    )

    assert result.final_status == "ok"
    assert any(warning.code == "validation_retry" for warning in result.warnings)
    correction_messages = [
        message.content
        for message in provider.calls[1]["messages"]
        if message.role == "user" and "macro_brief_validation_error" in message.content
    ]
    assert correction_messages
    assert "confirmed_facts[f2].unknown_evidence_ids:ev_credit" in correction_messages[0]


def test_finalize_claim_evidence_gate_retries_unbound_reported_number():
    invalid_payload = brief_payload()
    invalid_payload["confirmed_facts"][1]["evidence_ids"] = ["ev_known_credit"]
    invalid_payload["confirmed_facts"][1]["value"] = 9.9
    fixed_payload = brief_payload()
    fixed_payload["confirmed_facts"][1]["evidence_ids"] = ["ev_known_credit"]
    fixed_payload["confirmed_facts"][1]["value"] = None
    fixed_payload["confirmed_facts"][1]["unit"] = None
    fixed_payload["confirmed_facts"][1]["as_of"] = None
    fixed_payload["confirmed_facts"][1]["statement"] = "Credit reporting remained a qualitative watch item."
    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-reported-number", invalid_payload)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("fixed-reported-number", fixed_payload)], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="reported-number-gate",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        evidence_ledger=_ledger(
            _evidence_record("ev_dgs10"),
            _evidence_record("ev_known_credit", tool_name="rag_retrieve", value=3.1),
        ),
    )

    assert result.final_status == "ok"
    assert any(warning.code == "validation_retry" for warning in result.warnings)
    correction_messages = [
        message.content
        for message in provider.calls[1]["messages"]
        if message.role == "user" and "macro_brief_validation_error" in message.content
    ]
    assert correction_messages
    assert "confirmed_facts[f2].reported_atomic_observation_mismatch" in correction_messages[0]


def test_finalize_with_evidence_ledger_adds_temporal_envelope_to_brief():
    payload = brief_payload()
    payload["confirmed_facts"][1]["as_of"] = "2026-06-26"
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call(payload=payload)], finish_reason="tool_calls")])

    result = run_agent(
        session_id="temporal-envelope",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        report_generated_at="2026-06-30T00:00:00Z",
        evidence_ledger=_ledger(
            _evidence_record("ev_dgs10", tool_name="treasury_curve", observation_date="2026-06-27"),
            _evidence_record(
                "ev_credit",
                tool_name="rag_retrieve",
                observation_date="2026-06-26",
                value=3.1,
            ),
        ),
    )

    assert result.final_status == "ok"
    assert result.brief is not None
    assert result.brief.report_generated_at == "2026-06-30T00:00:00Z"
    assert result.brief.market_data_cutoff == "2026-06-27"
    assert result.brief.policy_data_cutoff == "2026-06-26"
    assert result.brief.macro_data_cutoff == "2026-06-26"


def test_finalize_with_evidence_ledger_rebuilds_source_list_server_side():
    payload = brief_payload()
    payload["confirmed_facts"][0]["source_id"] = "fake_llm_source"
    payload["confirmed_facts"][1]["source_id"] = "another_fake_source"
    payload["confirmed_facts"][1]["as_of"] = "2026-06-26"
    payload["source_list"] = [
        {
            "id": "fake_llm_source",
            "url": "https://example.com/llm-invented",
            "accessed_at": "1999-01-01",
        }
    ]
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call(payload=payload)], finish_reason="tool_calls")])

    result = run_agent(
        session_id="server-side-source-list",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        evidence_ledger=_ledger(
            _evidence_record(
                "ev_dgs10",
                tool_name="treasury_curve",
                observation_date="2026-06-27",
            ).model_copy(update={"canonical_url": "https://fred.stlouisfed.org/series/DGS10"}),
            _evidence_record(
                "ev_credit",
                tool_name="rag_retrieve",
                observation_date="2026-06-26",
                value=3.1,
            ).model_copy(update={"rag_doc_id": "credit_snapshot"}),
        ),
    )

    assert result.final_status == "ok"
    assert result.brief is not None
    assert [fact.source_id for fact in result.brief.confirmed_facts] == [
        "src_ev_dgs10",
        "src_ev_credit",
    ]
    assert [source.id for source in result.brief.source_list] == [
        "src_ev_dgs10",
        "src_ev_credit",
    ]
    assert result.brief.source_list[0].url == "https://fred.stlouisfed.org/series/DGS10"
    assert result.brief.source_list[1].rag_doc_id == "credit_snapshot"


def test_tool_results_register_into_evidence_ledger_before_finalize():
    provider = EvidenceAwareProvider()

    result = run_agent(
        session_id="auto-ledger",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_curve_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["treasury_curve", FINALIZE_TOOL_NAME],
        evidence_ledger=RunEvidenceLedger(run_id="auto-ledger"),
    )

    assert result.final_status == "ok"
    assert result.brief is not None
    evidence_ids = result.brief.confirmed_facts[0].evidence_ids
    assert evidence_ids
    tool_messages = [
        message for message in provider.calls[1]["messages"] if message.role == "tool"
    ]
    tool_payload = json.loads(tool_messages[0].content)
    assert tool_payload["content"]["registered_evidence_ids"] == evidence_ids
    assert tool_payload["content"]["points"][0]["evidence_id"] == evidence_ids[0]
    event = next(event for event in result.events if event.type == "tool_result")
    assert event.data["evidence_ids"] == evidence_ids
    assert result.brief.source_list[0].url == "https://fred.stlouisfed.org/series/DGS10"


def test_validation_retry_message_does_not_leak_input_values():
    invalid_payload = brief_payload()
    invalid_payload["market_state"][0]["symbol"] = "SECRET_INPUT_VALUE"
    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-final", invalid_payload)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("good-final")], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s6",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    retry_messages = [
        message.content
        for message in provider.calls[1]["messages"]
        if message.role == "user" and "macro_brief_validation_error" in message.content
    ]
    assert retry_messages
    assert "SECRET_INPUT_VALUE" not in retry_messages[0]


def test_provider_call_caps_max_tokens_by_remaining_budget():
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])

    result = run_agent(
        session_id="token-preflight",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(
            max_tokens_per_call=8192,
            research_max_tokens_per_call=4000,
        ),
        budget=AgentBudget(max_tokens_total=10, tokens_used=7),
    )

    assert result.final_status == "ok"
    assert provider.calls[0]["max_tokens"] == 3


def test_two_phase_default_switches_after_two_plain_turns_to_finalize_only():
    provider = MockProvider(
        [
            ChatResponse(content="research note"),
            ChatResponse(content="second note"),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s7",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert tool_names_from_call(provider.calls[2]) == [FINALIZE_TOOL_NAME]
    assert any(
        message.role == "system" and "Research phase is closed." in message.content
        for message in provider.calls[2]["messages"]
    )
    assert any(event.type == "agent_phase" and event.data["reason"] == "no_tool_calls" for event in result.events)


def test_two_phase_research_max_steps_switches_to_finalize_only():
    dispatches: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="call-1", name="dashboard_query", arguments={"series": "DGS10"})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s8",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dispatches),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(research_max_steps=1),
    )

    assert result.final_status == "ok"
    assert dispatches == [{"series": "DGS10"}]
    assert tool_names_from_call(provider.calls[1]) == [FINALIZE_TOOL_NAME]


def test_force_writing_phase_starts_with_finalize_only():
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])

    result = run_agent(
        session_id="s9",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(force_writing_phase=True),
    )

    assert result.final_status == "ok"
    assert tool_names_from_call(provider.calls[0]) == [FINALIZE_TOOL_NAME]
    assert any(
        message.role == "system" and "Research phase is closed." in message.content
        for message in provider.calls[0]["messages"]
    )


def test_mixed_finalize_call_is_rejected_without_dispatching_other_tools():
    dashboard_calls: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="dash-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    ),
                    finalize_call("mixed-final"),
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="mixed-finalize",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dashboard_calls),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(two_phase_mode=False),
    )

    tool_messages = [
        json.loads(message.content)
        for message in provider.calls[1]["messages"]
        if message.role == "tool"
    ]

    assert result.final_status == "ok"
    assert dashboard_calls == []
    assert tool_names_from_call(provider.calls[1]) == [FINALIZE_TOOL_NAME]
    assert any(warning.code == "invalid_mixed_finalize_call" for warning in result.warnings)
    assert {message["error_code"] for message in tool_messages} == {
        "invalid_mixed_finalize_call"
    }


def test_two_phase_can_be_disabled_for_single_loop_behavior():
    provider = MockProvider(
        [
            ChatResponse(content="research note"),
            ChatResponse(content="second note"),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s10",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(two_phase_mode=False),
    )

    assert result.final_status == "ok"
    assert tool_names_from_call(provider.calls[2]) == ["dashboard_query", FINALIZE_TOOL_NAME]
