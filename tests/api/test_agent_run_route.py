from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app_backend.main import (
    app,
    get_agent_run_service,
    get_holdings_consent_service,
    get_holdings_context_service,
)
from app_backend.schemas.agent_api import AgentRunRequest
from app_backend.services.agent_api_service import AgentRunService
from app_backend.services.agent_runtime import AgentSessionResult, run_agent
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME
from app_backend.services.agent_tool_registry import ToolSpec
from app_backend.services.agent_trace_service import AgentTraceService
from app_backend.services.holdings_consent_service import HoldingsConsentService
from app_backend.services.holdings_external_context_service import HoldingsExternalContextService
from app_backend.services.llm_provider_adapter import ChatResponse
from tests.ai.test_agent_runtime_mocked import MockProvider, brief_payload, finalize_call, make_registry


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    return TestClient(app)


def _service(
    tmp_path: Path,
    provider: MockProvider,
    *,
    holdings_consent_service: HoldingsConsentService | None = None,
    holdings_context_service: HoldingsExternalContextService | None = None,
) -> AgentRunService:
    def registry_factory(confirm_external_search: bool):
        registry = make_registry()
        if confirm_external_search:
            for name in ["search_tavily", "commodity_quote", "quote_dxy"]:
                registry.register(
                    ToolSpec(
                        name=name,
                        description=f"Fake {name} tool.",
                        parameters_schema={
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": True,
                        },
                        handler=lambda args: {"results": [], "args": args},
                    )
                )
        return registry

    return AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 6, 30),
        holdings_consent_service=holdings_consent_service,
        holdings_context_service=holdings_context_service,
        enable_evidence_ledger=False,
    )


def _install_service(service: AgentRunService) -> None:
    app.dependency_overrides[get_agent_run_service] = lambda: service


def _install_consent_service(service: HoldingsConsentService) -> None:
    app.dependency_overrides[get_holdings_consent_service] = lambda: service


def _install_holdings_context_service(service: HoldingsExternalContextService) -> None:
    app.dependency_overrides[get_holdings_context_service] = lambda: service


def test_agent_run_service_enables_evidence_ledger_by_default(tmp_path):
    captured = {}

    def fake_runtime(**kwargs):
        captured["evidence_ledger"] = kwargs["evidence_ledger"]
        return AgentSessionResult(
            session_id=kwargs["session_id"],
            final_status="incomplete",
            steps=0,
        )

    service = AgentRunService(
        provider_factory=lambda: MockProvider([]),
        registry_factory=lambda _confirm_external_search: make_registry(),
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        runtime_fn=fake_runtime,
        current_date_provider=lambda: date(2026, 6, 30),
    )

    response = service.run(
        AgentRunRequest(
            session_id="ledger-default",
            user_question="Build a macro brief.",
        )
    )

    assert response.session_id == "ledger-default"
    assert captured["evidence_ledger"].run_id == "ledger-default"


def test_agent_run_service_can_pin_enabled_tool_names(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=lambda _confirm_external_search: make_registry(),
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        runtime_fn=run_agent,
        current_date_provider=lambda: date(2026, 6, 30),
        enable_evidence_ledger=False,
        enabled_tool_names=[FINALIZE_TOOL_NAME],
    )

    response = service.run(
        AgentRunRequest(
            session_id="pinned-tools",
            user_question="Build a macro brief.",
        )
    )

    tool_names = [tool["function"]["name"] for tool in provider.calls[0]["tools"]]
    system_prompt = provider.calls[0]["messages"][0].content
    assert response.final_status == "ok"
    assert tool_names == [FINALIZE_TOOL_NAME]
    assert "dashboard_query" not in system_prompt
    assert FINALIZE_TOOL_NAME in system_prompt


def test_agent_run_endpoint_returns_rendered_public_brief(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-1",
            "user_question": "Build a macro brief.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "agent-session-1"
    assert body["final_status"] == "ok"
    assert body["source_visibility_mode"] == "public"
    assert "rendered_markdown" in body
    assert body["brief"]["core_conclusion"] == "Macro environment remains balanced."
    assert body["sources"][0]["url"] == "https://fred.stlouisfed.org/series/DGS10"
    assert "研究辅助输出" in body["rendered_markdown"]
    assert "非自动投资决策" in body["rendered_markdown"]
    assert "需要用户审阅" in body["rendered_markdown"]
    assert "credit_snapshot" not in body["rendered_markdown"]
    assert "Build a macro brief." not in response.text


def test_agent_run_endpoint_debug_mode_returns_internal_sources(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-2",
            "user_question": "Build a macro brief.",
            "source_visibility_mode": "debug",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_visibility_mode"] == "debug"
    assert any(source["origin"] == "rag" for source in body["sources"])
    assert "rag_doc_id=credit_snapshot" in body["source_markdown"]


def test_agent_run_without_search_confirmation_does_not_expose_search_tool(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-3",
            "user_question": "latest geopolitical oil news",
            "confirm_external_search": False,
        },
    )

    assert response.status_code == 200
    tool_names = [
        tool["function"]["name"]
        for tool in provider.calls[0]["tools"]
    ]
    assert "search_tavily" not in tool_names
    assert "commodity_quote" not in tool_names
    assert "quote_dxy" not in tool_names
    assert "current_public_news" in response.json()["missing_topics"]


def test_agent_run_with_search_confirmation_exposes_search_tool_to_runtime(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-4",
            "user_question": "latest geopolitical oil news",
            "confirm_external_search": True,
        },
    )

    assert response.status_code == 200
    tool_names = [
        tool["function"]["name"]
        for tool in provider.calls[0]["tools"]
    ]
    assert "search_tavily" in tool_names
    assert "commodity_quote" in tool_names
    assert "quote_dxy" in tool_names
    body = response.json()
    assert body["search_required"] is True
    assert any(
        need["topic"] == "current_public_news" and need["status"] == "search_required"
        for need in body["information_plan"]["needs"]
    )


def test_default_agent_run_service_wires_registry_without_eager_external_calls():
    service = get_agent_run_service()

    local_registry = service.registry_factory(False)
    external_registry = service.registry_factory(True)

    assert FINALIZE_TOOL_NAME in local_registry.names()
    assert "rag_retrieve" in local_registry.names()
    assert "search_tavily" not in local_registry.names()
    assert "commodity_quote" not in local_registry.names()
    assert "quote_dxy" not in local_registry.names()
    assert "search_tavily" in external_registry.names()
    assert "commodity_quote" in external_registry.names()
    assert "quote_dxy" in external_registry.names()
    assert service.provider_factory().name == "deepseek"


def test_agent_run_rejects_holdings_without_consent_token(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    consent_service = HoldingsConsentService()
    _install_service(
        _service(
            tmp_path,
            provider,
            holdings_consent_service=consent_service,
            holdings_context_service=HoldingsExternalContextService(lambda _session_id: {"positions": []}),
        )
    )

    response = _client().post(
        "/api/agent/run",
        json={
            "user_question": "Build a macro brief.",
            "include_holdings": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "holdings_consent_token_required"


def test_agent_capabilities_report_unwired_holdings_by_default():
    response = _client().get("/api/agent/capabilities")

    assert response.status_code == 200
    assert response.json()["holdings_external_context"] == {
        "enabled": False,
        "reason_code": "holdings_snapshot_backend_not_wired",
    }


def test_agent_capabilities_report_wired_holdings_when_provider_exists():
    _install_holdings_context_service(HoldingsExternalContextService(lambda _session_id: {"positions": []}))

    response = _client().get("/api/agent/capabilities")

    assert response.status_code == 200
    assert response.json()["holdings_external_context"] == {
        "enabled": True,
        "reason_code": None,
    }


def test_default_agent_run_rejects_holdings_activation_when_snapshot_provider_is_unwired():
    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-default-unwired",
            "user_question": "Build a macro brief.",
            "include_holdings": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "holdings_snapshot_backend_not_wired"


def test_agent_run_rejects_holdings_when_snapshot_provider_is_unwired(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    consent_service = HoldingsConsentService()
    token = consent_service.issue(session_id="agent-session-holdings-unwired").token
    _install_service(
        _service(
            tmp_path,
            provider,
            holdings_consent_service=consent_service,
            holdings_context_service=HoldingsExternalContextService(),
        )
    )

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-holdings-unwired",
            "user_question": "Build a macro brief.",
            "include_holdings": True,
            "holdings_consent_token": token,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "holdings_snapshot_backend_not_wired"
    assert consent_service.validate(token, session_id="agent-session-holdings-unwired").token == token


def test_agent_run_with_consent_injects_holdings_server_side_without_response_leak(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    consent_service = HoldingsConsentService()
    token = consent_service.issue(session_id="agent-session-holdings").token
    context_service = HoldingsExternalContextService(
        lambda _session_id: {
            "positions": [{"ticker": "SPY", "quantity": 10, "market_value": 5000}],
            "asset_class_breakdown": {"equity": 1.0},
        }
    )
    _install_service(
        _service(
            tmp_path,
            provider,
            holdings_consent_service=consent_service,
            holdings_context_service=context_service,
        )
    )

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-holdings",
            "user_question": "Build a macro brief.",
            "include_holdings": True,
            "holdings_consent_token": token,
        },
    )

    assert response.status_code == 200
    system_prompt = provider.calls[0]["messages"][0].content
    assert "explicitly approved for this run only" in system_prompt
    assert '"ticker": "SPY"' in system_prompt
    assert "market_value" not in response.text
    assert "5000" not in response.text
    with pytest.raises(Exception):
        consent_service.validate(token, session_id="agent-session-holdings")


def test_agent_run_blocks_model_holdings_output_disclosure(tmp_path):
    leaking_payload = brief_payload()
    leaking_payload["core_conclusion"] = "SPY market value is 5000."
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call("leak-final", leaking_payload)], finish_reason="tool_calls")])
    consent_service = HoldingsConsentService()
    token = consent_service.issue(session_id="agent-session-holdings-leak").token
    context_service = HoldingsExternalContextService(
        lambda _session_id: {
            "positions": [{"ticker": "SPY", "quantity": 10, "market_value": 5000}],
            "asset_class_breakdown": {"equity": 1.0},
        }
    )
    _install_service(
        _service(
            tmp_path,
            provider,
            holdings_consent_service=consent_service,
            holdings_context_service=context_service,
        )
    )

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-holdings-leak",
            "user_question": "Build a macro brief.",
            "include_holdings": True,
            "holdings_consent_token": token,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["final_status"] == "validation_failed"
    assert body["brief"] is None
    assert body["partial_brief"] is None
    assert body["warnings"][0]["code"] == "holdings_output_disclosure_blocked"
    assert "5000" not in response.text


def test_agent_run_rejects_consent_token_when_holdings_disabled(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "user_question": "Build a macro brief.",
            "holdings_consent_token": "token_1234567890123456",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "holdings_consent_token_without_include_holdings"


def test_agent_run_request_schema_defaults_are_public_and_local_first():
    request = AgentRunRequest(
        user_question="Build a macro brief.",
    )

    assert request.source_visibility_mode == "public"
    assert request.confirm_external_search is False
    assert request.include_holdings is False
    assert request.holdings_consent_token is None
    assert request.output_mode == "macro_brief_strict"


def test_agent_run_natural_answer_uses_planned_tools_before_writer(tmp_path):
    provider = MockProvider(
        [
            ChatResponse(
                content=(
                    "结论：SPY 的本地报价证据已经可用 。"
                    "边界：非个股操作 非概率胜率 非收益预测 非动态择时 非黑盒最优化"
                )
            )
        ]
    )
    tool_calls: list[dict] = []

    def registry_factory(_confirm_external_search: bool):
        registry = make_registry()
        registry.register(
            ToolSpec(
                name="quote_etf",
                description="Fake ETF quote.",
                parameters_schema={"type": "object"},
                handler=lambda args: tool_calls.append(args) or {
                    "quotes": [
                        {
                            "symbol": args["symbols"][0],
                            "value": 640.5,
                            "unit": "USD",
                            "status": "ok",
                            "observation_date": "2026-07-01",
                        }
                    ]
                },
            )
        )
        return registry

    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 7, 2),
    )

    response = service.run(
        AgentRunRequest(
            session_id="natural-answer",
            user_question="请结合 SPY/QQQ 看当前 equity market。",
            output_mode="natural_answer",
        )
    )

    assert response.final_status == "ok"
    assert response.output_mode == "natural_answer"
    assert response.natural_answer == response.rendered_markdown
    assert response.brief is None
    assert response.partial_brief is None
    assert tool_calls[0] == {"symbols": ["SPY"]}
    writer_call = provider.calls[0]
    assert writer_call["tools"] == []
    assert writer_call["response_format"] is None
    assert "Evidence pack JSON" in writer_call["messages"][1].content
    assert "ETF quote SPY" in writer_call["messages"][1].content


def test_agent_run_natural_answer_blocks_unknown_evidence_ids(tmp_path):
    provider = MockProvider(
        [
            ChatResponse(
                content=(
                    "Conclusion: unsupported citation [ev_2]. "
                    "non-stock-action non-probability-win non-return-forecast "
                    "non-dynamic-timing non-black-box-optimization"
                )
            )
        ]
    )

    def registry_factory(_confirm_external_search: bool):
        registry = make_registry()
        registry.register(
            ToolSpec(
                name="quote_etf",
                description="Fake ETF quote.",
                parameters_schema={"type": "object"},
                handler=lambda args: {
                    "quotes": [
                        {
                            "symbol": args["symbols"][0],
                            "value": 640.5,
                            "unit": "USD",
                            "status": "ok",
                            "observation_date": "2026-07-01",
                        }
                    ]
                },
            )
        )
        return registry

    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 7, 2),
    )

    response = service.run(
        AgentRunRequest(
            session_id="natural-answer-unknown-evidence-id",
            user_question="Please discuss SPY.",
            output_mode="natural_answer",
        )
    )

    assert response.final_status == "validation_failed"
    assert response.natural_answer == ""
    assert response.rendered_markdown == ""
    assert response.warnings[0].code == "natural_answer_unknown_evidence_ids"
    assert "ev_2" in response.warnings[0].message


def test_agent_run_natural_answer_corrects_false_unavailable_quote_claim(tmp_path):
    provider = MockProvider(
        [
            ChatResponse(
                content=(
                    "ETF market data unavailable: SPY and QQQ missing. "
                    "non-stock-action non-probability-win non-return-forecast "
                    "non-dynamic-timing non-black-box-optimization"
                )
            )
        ]
    )

    def registry_factory(_confirm_external_search: bool):
        registry = make_registry()
        registry.register(
            ToolSpec(
                name="quote_etf",
                description="Fake ETF quote.",
                parameters_schema={"type": "object"},
                handler=lambda args: {
                    "quotes": [
                        {
                            "symbol": args["symbols"][0],
                            "value": 640.5,
                            "unit": "USD",
                            "status": "ok",
                            "observation_date": "2026-07-01",
                        }
                    ]
                },
            )
        )
        return registry

    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 7, 2),
    )

    response = service.run(
        AgentRunRequest(
            session_id="natural-answer-false-unavailable",
            user_question="Please discuss SPY.",
            output_mode="natural_answer",
        )
    )

    assert response.final_status == "ok"
    assert response.warnings[0].code == "natural_answer_corrected_available_evidence"
    assert response.natural_answer == response.rendered_markdown
    assert "ETF market data unavailable" not in response.natural_answer
    assert "SPY" in response.natural_answer
    assert "ev_quote_etf_" in response.natural_answer


def test_agent_run_natural_answer_budget_allows_full_quote_mix(tmp_path):
    provider = MockProvider(
        [
            ChatResponse(
                content=(
                    "结论：完整报价组合已执行。"
                    "非个股操作 非概率胜率 非收益预测 非动态择时 非黑盒最优化"
                )
            )
        ]
    )
    tool_calls: list[str] = []

    def registry_factory(_confirm_external_search: bool):
        registry = make_registry()
        registry.register(
            ToolSpec(
                name="quote_etf",
                description="Fake ETF quote.",
                parameters_schema={"type": "object"},
                handler=lambda args: tool_calls.append(f"quote_etf:{args['symbols'][0]}") or {
                    "quotes": [
                        {
                            "symbol": args["symbols"][0],
                            "value": 100.0,
                            "unit": "USD",
                            "status": "ok",
                            "observation_date": "2026-07-01",
                        }
                    ]
                },
            )
        )
        registry.register(
            ToolSpec(
                name="treasury_curve",
                description="Fake curve.",
                parameters_schema={"type": "object"},
                handler=lambda _args: tool_calls.append("treasury_curve") or {
                    "points": [
                        {
                            "tenor": "10Y",
                            "source_series": "DGS10",
                            "value": 4.3,
                            "unit": "%",
                            "observation_date": "2026-07-01",
                            "status": "ok",
                        }
                    ]
                },
            )
        )
        registry.register(
            ToolSpec(
                name="quote_dxy",
                description="Fake DXY.",
                parameters_schema={"type": "object"},
                handler=lambda _args: tool_calls.append("quote_dxy") or {
                    "status": "ok",
                    "series_id": "DTWEXBGS",
                    "value": 120.0,
                    "unit": "index",
                    "observation_date": "2026-07-01",
                    "source": "FRED",
                    "name": "broad trade-weighted USD index",
                },
            )
        )
        return registry

    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 7, 2),
    )

    response = service.run(
        AgentRunRequest(
            session_id="natural-answer-budget",
            user_question="请结合 SPY/QQQ/SHY/GLD、长端利率和美元指数做自然回答。",
            confirm_external_search=True,
            output_mode="natural_answer",
        )
    )

    assert response.final_status == "ok"
    assert response.warnings == []
    assert tool_calls == [
        "quote_etf:SPY",
        "quote_etf:QQQ",
        "quote_etf:SHY",
        "quote_etf:GLD",
        "treasury_curve",
        "quote_dxy",
    ]


def test_agent_run_natural_answer_blocks_holdings_text_leak(tmp_path):
    provider = MockProvider([ChatResponse(content="账户持仓市值是 5000。")])
    consent_service = HoldingsConsentService()
    token = consent_service.issue(session_id="natural-answer-leak").token
    context_service = HoldingsExternalContextService(
        lambda _session_id: {
            "positions": [{"ticker": "SPY", "quantity": 10, "market_value": 5000}],
            "asset_class_breakdown": {"equity": 1.0},
        }
    )
    _install_service(
        _service(
            tmp_path,
            provider,
            holdings_consent_service=consent_service,
            holdings_context_service=context_service,
        )
    )

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "natural-answer-leak",
            "user_question": "请自然回答 portfolio 风险。",
            "include_holdings": True,
            "holdings_consent_token": token,
            "output_mode": "natural_answer",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["final_status"] == "validation_failed"
    assert body["natural_answer"] == ""
    assert body["warnings"][0]["code"] == "holdings_output_disclosure_blocked"
    assert "5000" not in response.text


def test_holdings_consent_endpoint_requires_explicit_confirmation():
    response = _client().post(
        "/api/agent/holdings-consent",
        json={"confirm_holdings_external_context": False},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "holdings_consent_confirmation_required"


def test_holdings_consent_endpoint_rejects_when_snapshot_provider_is_unwired():
    consent_service = HoldingsConsentService(token_factory=lambda: "token_1234567890123456")
    _install_consent_service(consent_service)

    response = _client().post(
        "/api/agent/holdings-consent",
        json={
            "session_id": "agent-session-consent",
            "confirm_holdings_external_context": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "holdings_snapshot_backend_not_wired"
    with pytest.raises(Exception):
        consent_service.validate("token_1234567890123456", session_id="agent-session-consent")


def test_holdings_consent_endpoint_issues_token_without_holdings_body():
    consent_service = HoldingsConsentService(token_factory=lambda: "token_1234567890123456")
    _install_consent_service(consent_service)
    _install_holdings_context_service(HoldingsExternalContextService(lambda _session_id: {"positions": []}))

    response = _client().post(
        "/api/agent/holdings-consent",
        json={
            "session_id": "agent-session-consent",
            "confirm_holdings_external_context": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "agent-session-consent"
    assert body["holdings_consent_token"] == "token_1234567890123456"
    assert body["ttl_seconds"] == 600
    assert "positions" not in response.text
    assert "market_value" not in response.text


def test_agent_run_rejects_client_supplied_current_date(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-current-date",
            "user_question": "Build a macro brief.",
            "current_date": "1999-01-01",
        },
    )

    assert response.status_code == 422
    assert not provider.calls


def test_agent_route_registered_without_forbidden_legacy_routes():
    paths = {route.path for route in app.routes}

    assert "/api/agent/holdings-consent" in paths
    assert "/api/agent/run" in paths
    assert "/api/chat" not in paths
    assert "/api/ai/tavily" not in paths
