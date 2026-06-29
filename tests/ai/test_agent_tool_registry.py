from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from app_backend.services.agent_tool_registry import (
    AgentToolRegistry,
    ToolResult,
    ToolSpec,
    build_f1_read_only_tools,
    make_dashboard_query_tool,
    make_evidence_lookup_tool,
    make_quote_etf_tool,
)


# ---------------------------------------------------------------------------
# Core registry behavior
# ---------------------------------------------------------------------------


def _echo_spec() -> ToolSpec:
    return ToolSpec(
        name="echo",
        description="Return the args unchanged.",
        parameters_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        handler=lambda args: {"echoed": args["value"]},
    )


def test_register_and_dispatch_basic():
    registry = AgentToolRegistry()
    registry.register(_echo_spec())

    assert registry.names() == ["echo"]
    result = registry.dispatch("echo", {"value": "hi"})

    assert isinstance(result, ToolResult)
    assert result.status == "ok"
    assert result.content == {"echoed": "hi"}


def test_duplicate_registration_raises():
    registry = AgentToolRegistry()
    registry.register(_echo_spec())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_echo_spec())


def test_dispatch_unknown_tool_returns_error_result():
    registry = AgentToolRegistry()
    result = registry.dispatch("nonexistent", {})

    assert result.status == "error"
    assert result.error_code == "unknown_tool"


def test_dispatch_handler_exception_wrapped():
    def boom(_args: dict[str, Any]) -> Any:
        raise RuntimeError("kaboom")

    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="boom",
            description="raises",
            parameters_schema={"type": "object", "properties": {}, "required": []},
            handler=boom,
        )
    )

    result = registry.dispatch("boom", {})
    assert result.status == "error"
    assert result.error_code == "handler_exception"
    assert "RuntimeError" in (result.error_message or "")


def test_dispatch_non_dict_args_rejected():
    registry = AgentToolRegistry()
    registry.register(_echo_spec())
    result = registry.dispatch("echo", ["not", "a", "dict"])  # type: ignore[arg-type]
    assert result.status == "error"
    assert result.error_code == "invalid_args_type"


def test_dispatch_non_serializable_result_rejected():
    def returns_set(_args: dict[str, Any]) -> Any:
        return {"set": {1, 2, 3}}  # set is not JSON-serializable

    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="bad",
            description="returns non-serializable",
            parameters_schema={"type": "object", "properties": {}, "required": []},
            handler=returns_set,
        )
    )
    result = registry.dispatch("bad", {})
    assert result.status == "error"
    assert result.error_code == "non_serializable_result"


def test_openai_schema_format():
    registry = AgentToolRegistry()
    registry.register(_echo_spec())
    schema = registry.openai_schema()

    assert len(schema) == 1
    assert schema[0]["type"] == "function"
    assert schema[0]["function"]["name"] == "echo"
    assert "parameters" in schema[0]["function"]


def test_tool_result_to_json_payload_ok():
    result = ToolResult(status="ok", content={"x": 1})
    assert result.to_json_payload() == {"status": "ok", "content": {"x": 1}}


def test_tool_result_to_json_payload_error():
    result = ToolResult(status="error", error_code="boom", error_message="msg")
    assert result.to_json_payload() == {
        "status": "error",
        "error_code": "boom",
        "error_message": "msg",
    }


# ---------------------------------------------------------------------------
# Tool-specific handlers (F1-1: dashboard_query, evidence_lookup, quote_etf,
# treasury_curve, calendar_lookup)
# ---------------------------------------------------------------------------


class _FakeSummary(BaseModel):
    overall_status: str = "ok"
    module_count: int = 6


def test_dashboard_query_handler_returns_jsonable():
    spec = make_dashboard_query_tool(lambda: _FakeSummary())

    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("dashboard_query", {})

    assert result.status == "ok"
    assert result.content == {"overall_status": "ok", "module_count": 6}


def test_dashboard_query_rejects_unexpected_args():
    spec = make_dashboard_query_tool(lambda: _FakeSummary())
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("dashboard_query", {"foo": "bar"})
    assert result.status == "error"
    assert result.error_code == "unexpected_args"


class _FakeEvidence(BaseModel):
    modules: list[dict[str, Any]]


def _build_fake_evidence() -> _FakeEvidence:
    return _FakeEvidence(
        modules=[
            {
                "module_key": "rate_pressure",
                "rows": [
                    {"metric_key": "dgs10", "value": 4.3},
                    {"metric_key": "dgs2", "value": 4.1},
                ],
            },
            {
                "module_key": "credit_pressure",
                "rows": [{"metric_key": "hy_oas", "value": 2.78}],
            },
        ]
    )


def test_evidence_lookup_returns_all_rows_when_no_filter():
    spec = make_evidence_lookup_tool(_build_fake_evidence)
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("evidence_lookup", {})

    assert result.status == "ok"
    assert result.content["row_count"] == 3


def test_evidence_lookup_filters_by_module_key():
    spec = make_evidence_lookup_tool(_build_fake_evidence)
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("evidence_lookup", {"module_key": "rate_pressure"})

    assert result.status == "ok"
    assert result.content["row_count"] == 2
    assert all(row["module_key"] == "rate_pressure" for row in result.content["rows"])


def test_evidence_lookup_filters_by_metric_key():
    spec = make_evidence_lookup_tool(_build_fake_evidence)
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("evidence_lookup", {"metric_key": "hy_oas"})

    assert result.status == "ok"
    assert result.content["row_count"] == 1
    assert result.content["rows"][0]["metric_key"] == "hy_oas"


def test_evidence_lookup_rejects_non_string_module_key():
    spec = make_evidence_lookup_tool(_build_fake_evidence)
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("evidence_lookup", {"module_key": 123})
    assert result.status == "error"
    assert result.error_code == "invalid_module_key"


@dataclass(frozen=True)
class _FakeQuote:
    symbol: str
    price: float


def test_quote_etf_uppercases_and_validates_symbols():
    captured: dict[str, Any] = {}

    def fake_quote_fn(symbols: list[str]) -> list[_FakeQuote]:
        captured["symbols"] = symbols
        return [_FakeQuote(symbol=s, price=100.0) for s in symbols]

    spec = make_quote_etf_tool(fake_quote_fn)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_etf", {"symbols": ["spy", "qqq"]})

    assert result.status == "ok"
    assert captured["symbols"] == ["SPY", "QQQ"]
    assert len(result.content["quotes"]) == 2


def test_quote_etf_rejects_unknown_symbol():
    spec = make_quote_etf_tool(lambda symbols: [])
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("quote_etf", {"symbols": ["AAPL"]})

    assert result.status == "error"
    assert result.error_code == "unknown_symbol"


def test_quote_etf_rejects_empty_list():
    spec = make_quote_etf_tool(lambda symbols: [])
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("quote_etf", {"symbols": []})

    assert result.status == "error"
    assert result.error_code == "invalid_symbols"


def test_quote_etf_rejects_missing_symbols_key():
    spec = make_quote_etf_tool(lambda symbols: [])
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("quote_etf", {})

    assert result.status == "error"
    assert result.error_code == "invalid_symbols"


# ---------------------------------------------------------------------------
# Bundled registry: build_f1_read_only_tools + register_all
# ---------------------------------------------------------------------------


def test_build_f1_read_only_tools_registers_all_five():
    bundle = build_f1_read_only_tools(
        summary_fn=lambda: _FakeSummary(),
        evidence_fn=_build_fake_evidence,
        quote_fn=lambda symbols: [_FakeQuote(symbol=s, price=1.0) for s in symbols],
        curve_fn=lambda: {"points": []},
        next_releases_fn=lambda window: [],
        events_by_name_fn=lambda name, limit: [],
    )

    registry = AgentToolRegistry()
    bundle.register_all(registry)

    assert registry.names() == [
        "calendar_lookup",
        "dashboard_query",
        "evidence_lookup",
        "quote_etf",
        "treasury_curve",
    ]

    schema = registry.openai_schema()
    assert len(schema) == 5
    for entry in schema:
        assert entry["type"] == "function"
        assert "name" in entry["function"]
        assert "parameters" in entry["function"]


def test_calendar_lookup_default_uses_next_releases():
    captured: dict[str, Any] = {}

    def next_releases(window: int) -> list[dict[str, Any]]:
        captured["window"] = window
        return [{"event_name": "CPI", "release_date": "2026-07-14"}]

    bundle = build_f1_read_only_tools(
        summary_fn=lambda: {},
        evidence_fn=lambda: {"modules": []},
        quote_fn=lambda symbols: [],
        curve_fn=lambda: {},
        next_releases_fn=next_releases,
        events_by_name_fn=lambda name, limit: [],
    )
    registry = AgentToolRegistry()
    bundle.register_all(registry)

    result = registry.dispatch("calendar_lookup", {"window_days": 14})
    assert result.status == "ok"
    assert result.content["mode"] == "next_releases"
    assert captured["window"] == 14


def test_calendar_lookup_with_event_name_uses_by_name():
    captured: dict[str, Any] = {}

    def by_name(name: str, limit: int) -> list[dict[str, Any]]:
        captured["name"] = name
        captured["limit"] = limit
        return [{"event_name": name, "release_date": "2026-06-14"}]

    bundle = build_f1_read_only_tools(
        summary_fn=lambda: {},
        evidence_fn=lambda: {"modules": []},
        quote_fn=lambda symbols: [],
        curve_fn=lambda: {},
        next_releases_fn=lambda window: [],
        events_by_name_fn=by_name,
    )
    registry = AgentToolRegistry()
    bundle.register_all(registry)

    result = registry.dispatch("calendar_lookup", {"event_name": "CPI", "limit": 3})
    assert result.status == "ok"
    assert result.content["mode"] == "by_name"
    assert captured == {"name": "CPI", "limit": 3}


def test_calendar_lookup_rejects_out_of_range_window():
    bundle = build_f1_read_only_tools(
        summary_fn=lambda: {},
        evidence_fn=lambda: {"modules": []},
        quote_fn=lambda symbols: [],
        curve_fn=lambda: {},
        next_releases_fn=lambda window: [],
        events_by_name_fn=lambda name, limit: [],
    )
    registry = AgentToolRegistry()
    bundle.register_all(registry)

    result = registry.dispatch("calendar_lookup", {"window_days": 0})
    assert result.status == "error"
    assert result.error_code == "invalid_window_days"

    result = registry.dispatch("calendar_lookup", {"limit": 999})
    assert result.status == "error"
    assert result.error_code == "invalid_limit"
