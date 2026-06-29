from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from app_backend.schemas.search_external import (
    SearchResponse,
    SearchResult,
    TavilySearchApiRequest,
)
from app_backend.services.agent_tool_registry import (
    FINALIZE_TOOL_NAME,
    TOOL_RESULT_MAX_CHARS,
    AgentToolRegistry,
    ToolResult,
    ToolSpec,
    build_f1_network_tools,
    build_f1_portfolio_tools,
    build_f1_read_only_tools,
    make_commodity_quote_tool,
    make_dashboard_query_tool,
    make_evidence_lookup_tool,
    make_finalize_macro_brief_tool,
    make_portfolio_overlay_tool,
    make_quote_dxy_tool,
    make_quote_etf_tool,
    make_rag_retrieve_tool,
    make_search_tavily_tool,
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


# ---------------------------------------------------------------------------
# F1-2 guarded network / retrieval tool tests
# ---------------------------------------------------------------------------

# -- search_tavily --------------------------------------------------------


def _ok_search_response() -> SearchResponse:
    return SearchResponse(
        results=[
            SearchResult(
                url="https://reuters.com/markets",
                title="Markets update",
                snippet="Yields rose.",
                domain="reuters.com",
            )
        ],
        search_available=True,
        guard_passed=True,
    )


def test_search_tavily_hardcodes_confirm_external_search_true():
    captured: list[TavilySearchApiRequest] = []

    def fake_execute(request: TavilySearchApiRequest) -> SearchResponse:
        captured.append(request)
        return _ok_search_response()

    spec = make_search_tavily_tool(fake_execute)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("search_tavily", {"query": "Fed outlook"})

    assert result.status == "ok"
    assert len(captured) == 1
    assert captured[0].confirm_external_search is True
    assert captured[0].query == "Fed outlook"
    assert captured[0].max_results == 5  # default


def test_search_tavily_returns_safe_passthrough_when_guard_blocked():
    blocked = SearchResponse(results=[], search_available=False, guard_passed=False)
    spec = make_search_tavily_tool(lambda req: blocked)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("search_tavily", {"query": "anything"})

    assert result.status == "ok"
    assert result.content["results"] == []
    assert result.content["search_available"] is False
    assert result.content["guard_passed"] is False
    assert result.content["result_count"] == 0


def test_search_tavily_propagates_max_results_and_domain_filter():
    captured: list[TavilySearchApiRequest] = []

    def fake_execute(request: TavilySearchApiRequest) -> SearchResponse:
        captured.append(request)
        return _ok_search_response()

    spec = make_search_tavily_tool(fake_execute)
    registry = AgentToolRegistry()
    registry.register(spec)

    registry.dispatch(
        "search_tavily",
        {"query": "FOMC", "max_results": 12, "domain_filter": ["reuters.com"]},
    )

    assert captured[0].max_results == 12
    assert captured[0].domain_filter == ["reuters.com"]


@pytest.mark.parametrize(
    "args, expected_code",
    [
        ({}, "invalid_query"),
        ({"query": ""}, "invalid_query"),
        ({"query": "   "}, "invalid_query"),
        ({"query": "x" * 501}, "invalid_query"),
        ({"query": "ok", "max_results": "5"}, "invalid_max_results"),
        ({"query": "ok", "max_results": 0}, "invalid_max_results"),
        ({"query": "ok", "max_results": 21}, "invalid_max_results"),
        ({"query": "ok", "domain_filter": ["", "ok"]}, "invalid_domain_filter"),
        ({"query": "ok", "domain_filter": "not-a-list"}, "invalid_domain_filter"),
    ],
)
def test_search_tavily_validation(args, expected_code):
    spec = make_search_tavily_tool(lambda req: _ok_search_response())
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("search_tavily", args)
    assert result.status == "error"
    assert result.error_code == expected_code


# -- rag_retrieve ---------------------------------------------------------


@dataclass(frozen=True)
class _FakeRetrievedChunk:
    doc_id: str
    chunk_index: int
    text: str
    rrf_score: float
    title: str
    doc_type: str
    source_domain: str
    external_llm_context_allowed: bool = True
    evidence_tier: str = "official_evidence"
    is_official_source: bool = True


def test_rag_retrieve_hardcodes_include_local_only_false():
    captured: dict[str, Any] = {}

    def fake_retrieve(query, *, top_k, doc_type_filter, include_local_only):
        captured["query"] = query
        captured["top_k"] = top_k
        captured["doc_type_filter"] = doc_type_filter
        captured["include_local_only"] = include_local_only
        return [
            _FakeRetrievedChunk(
                doc_id="d1", chunk_index=0, text="hello", rrf_score=0.5,
                title="T", doc_type="policy_doc", source_domain="federalreserve.gov",
            )
        ]

    spec = make_rag_retrieve_tool(fake_retrieve)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("rag_retrieve", {"query": "yield curve"})

    assert result.status == "ok"
    assert captured["include_local_only"] is False
    assert captured["query"] == "yield curve"
    assert captured["top_k"] == 5
    assert captured["doc_type_filter"] is None
    assert result.content["chunk_count"] == 1
    assert "external_llm_context_allowed" not in result.content["chunks"][0]


def test_rag_retrieve_passes_top_k_and_doc_type():
    captured: dict[str, Any] = {}

    def fake_retrieve(query, *, top_k, doc_type_filter, include_local_only):
        captured.update(locals())
        return []

    spec = make_rag_retrieve_tool(fake_retrieve)
    registry = AgentToolRegistry()
    registry.register(spec)

    registry.dispatch("rag_retrieve", {"query": "fomc", "top_k": 8, "doc_type": "policy_doc"})

    assert captured["top_k"] == 8
    assert captured["doc_type_filter"] == "policy_doc"


def test_rag_retrieve_empty_results_returns_empty_chunk_list():
    spec = make_rag_retrieve_tool(lambda q, **kw: [])
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("rag_retrieve", {"query": "no match"})

    assert result.status == "ok"
    assert result.content == {"chunks": [], "chunk_count": 0}


@pytest.mark.parametrize(
    "args, expected_code",
    [
        ({}, "invalid_query"),
        ({"query": ""}, "invalid_query"),
        ({"query": "x" * 501}, "invalid_query"),
        ({"query": "ok", "top_k": 0}, "invalid_top_k"),
        ({"query": "ok", "top_k": 21}, "invalid_top_k"),
        ({"query": "ok", "top_k": "5"}, "invalid_top_k"),
        ({"query": "ok", "doc_type": 123}, "invalid_doc_type"),
    ],
)
def test_rag_retrieve_validation(args, expected_code):
    spec = make_rag_retrieve_tool(lambda q, **kw: [])
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("rag_retrieve", args)
    assert result.status == "error"
    assert result.error_code == expected_code


# -- commodity_quote ------------------------------------------------------


def test_commodity_quote_brent_passthrough():
    from app_backend.schemas.commodity_quote import CommodityQuoteSnapshot

    captured: list[str] = []

    def fake_quote(benchmark: str):
        captured.append(benchmark)
        return CommodityQuoteSnapshot(
            benchmark=benchmark,
            value_usd_per_barrel=82.5,
            unit="USD/bbl",
            status="observed",
            source_url="https://reuters.com/markets/oil",
            source_domain="reuters.com",
            source_title="Brent steady",
        )

    spec = make_commodity_quote_tool(fake_quote)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("commodity_quote", {"benchmark": "Brent"})  # case-insens

    assert result.status == "ok"
    assert captured == ["brent"]
    assert result.content["benchmark"] == "brent"
    assert result.content["value_usd_per_barrel"] == 82.5


def test_commodity_quote_wti_passthrough_and_unavailable_status():
    from app_backend.schemas.commodity_quote import CommodityQuoteSnapshot

    def fake_quote(benchmark: str):
        return CommodityQuoteSnapshot(
            benchmark=benchmark,
            status="unavailable",
            reason_code="no_safe_price_match",
        )

    spec = make_commodity_quote_tool(fake_quote)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("commodity_quote", {"benchmark": "wti"})

    assert result.status == "ok"
    assert result.content["status"] == "unavailable"
    assert result.content["reason_code"] == "no_safe_price_match"


@pytest.mark.parametrize(
    "args, expected_code",
    [
        ({}, "invalid_benchmark"),
        ({"benchmark": ""}, "invalid_benchmark"),
        ({"benchmark": "gold"}, "invalid_benchmark"),
        ({"benchmark": 123}, "invalid_benchmark"),
    ],
)
def test_commodity_quote_rejects_invalid_benchmark(args, expected_code):
    spec = make_commodity_quote_tool(lambda b: None)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("commodity_quote", args)
    assert result.status == "error"
    assert result.error_code == expected_code


# -- bundle ---------------------------------------------------------------


def test_build_f1_network_tools_registers_all_three():
    bundle = build_f1_network_tools(
        search_execute_fn=lambda req: _ok_search_response(),
        rag_retrieve_fn=lambda q, **kw: [],
        commodity_quote_fn=lambda b: {"benchmark": b, "status": "unavailable",
                                      "reason_code": "search_unavailable"},
    )
    registry = AgentToolRegistry()
    bundle.register_all(registry)

    assert sorted(registry.names()) == ["commodity_quote", "rag_retrieve", "search_tavily"]


def test_f1_network_tools_have_openai_schema():
    bundle = build_f1_network_tools(
        search_execute_fn=lambda req: _ok_search_response(),
        rag_retrieve_fn=lambda q, **kw: [],
        commodity_quote_fn=lambda b: {"benchmark": b, "status": "observed",
                                      "value_usd_per_barrel": 1.0, "unit": "USD/bbl",
                                      "source_url": "https://reuters.com/x",
                                      "source_domain": "reuters.com"},
    )
    schemas = [
        bundle.search_tavily.to_openai_schema(),
        bundle.rag_retrieve.to_openai_schema(),
        bundle.commodity_quote.to_openai_schema(),
    ]
    for schema in schemas:
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "parameters" in schema["function"]


# ---------------------------------------------------------------------------
# F1-3 portfolio / DXY / finalize tool tests
# ---------------------------------------------------------------------------


def _full_portfolio_snapshot() -> dict[str, Any]:
    # Shape mirrors portfolio_engine.generate_portfolio_snapshot output.
    return {
        # raw dollar amounts — MUST be dropped by the tool layer
        "total_assets": 354222.0,
        "invested_assets": 320000.0,
        "cash": 34222.0,
        "total_account_value": 354222.0,
        "invested_asset_value": 320000.0,
        "cash_reserve_value": 34222.0,
        "total_profit_loss": 12345.67,
        # per-holding detail with cost basis / P/L — MUST be dropped
        "holdings": [
            {
                "asset_name": "SPY",
                "current_value": 182247.0,
                "cost_basis": 170000.0,
                "profit_loss": 12247.0,
                "updated_at": "2026-06-29",
            }
        ],
        "aggregated_by_asset_class": {"large_cap": {"current_value": 252899.0}},
        # safe fields — MUST be returned
        "weights_ex_cash": {"large_cap": 0.703, "bond": 0.185, "gold": 0.101},
        "target_allocation": {"large_cap": 0.70, "bond": 0.20, "gold": 0.10},
        "deviation": {"large_cap": 0.003, "bond": -0.015, "gold": 0.001},
        "deviation_flags": {"large_cap": "ok", "bond": "watch", "gold": "ok"},
        "holdings_freshness_status": "fresh",
        "holdings_updated_at_status": "fresh",
        "holdings_age_days": 0,
        "holdings_row_count": 4,
        "holdings_updated_at": "2026-06-29",
        "holdings_updated_at_values": ["2026-06-29"],
        # DCA — MUST be dropped
        "dca_budget_check": {"min": 1000, "max": 5000},
        "dca_daily_plan": {"daily": 200},
        "notes": ["descriptive only"],
    }


def test_portfolio_overlay_strips_dollar_amounts_and_holdings():
    spec = make_portfolio_overlay_tool(_full_portfolio_snapshot)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("portfolio_overlay", {})

    assert result.status == "ok"
    overlay = result.content
    # safe fields included
    assert "weights_ex_cash" in overlay
    assert "target_allocation" in overlay
    assert "deviation" in overlay
    assert "deviation_flags" in overlay
    assert overlay["holdings_freshness_status"] == "fresh"
    assert overlay["available"] is True
    # forbidden fields stripped
    for forbidden in (
        "total_assets",
        "invested_assets",
        "cash",
        "total_account_value",
        "invested_asset_value",
        "cash_reserve_value",
        "total_profit_loss",
        "holdings",
        "aggregated_by_asset_class",
        "dca_budget_check",
        "dca_daily_plan",
        "holdings_updated_at_values",
    ):
        assert forbidden not in overlay, f"{forbidden} must not reach the LLM"


def test_portfolio_overlay_serialized_form_has_no_dollar_markers():
    """Final JSON form must contain no raw dollar amounts at all."""
    import json

    spec = make_portfolio_overlay_tool(_full_portfolio_snapshot)
    registry = AgentToolRegistry()
    registry.register(spec)
    result = registry.dispatch("portfolio_overlay", {})

    text = json.dumps(result.content)
    for amount in ("182247", "354222", "12345.67", "170000", "cost_basis", "profit_loss"):
        assert amount not in text


def test_portfolio_overlay_rejects_unexpected_args():
    spec = make_portfolio_overlay_tool(_full_portfolio_snapshot)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("portfolio_overlay", {"foo": "bar"})

    assert result.status == "error"
    assert result.error_code == "unexpected_args"


def test_portfolio_overlay_unavailable_when_snapshot_returns_non_dict():
    spec = make_portfolio_overlay_tool(lambda: None)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("portfolio_overlay", {})

    assert result.status == "ok"
    assert result.content == {"available": False, "reason": "portfolio_snapshot_unavailable"}


def test_portfolio_overlay_marks_available_false_when_empty_summary():
    spec = make_portfolio_overlay_tool(lambda: {"holdings_row_count": 0})
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("portfolio_overlay", {})

    assert result.status == "ok"
    assert result.content["available"] is False


# -- quote_dxy ------------------------------------------------------------


def test_quote_dxy_calls_fred_with_dtwexbgs():
    captured: list[tuple[str, int]] = []

    def fake_fred(series_id: str, limit: int):
        captured.append((series_id, limit))
        return {
            "status": "ok",
            "data": [{"date": "2026-06-27", "value": 102.45}],
        }

    spec = make_quote_dxy_tool(fake_fred)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_dxy", {})

    assert result.status == "ok"
    assert captured == [("DTWEXBGS", 10)]
    assert result.content == {
        "status": "ok",
        "series_id": "DTWEXBGS",
        "value": 102.45,
        "observation_date": "2026-06-27",
        "source": "FRED",
        "name": "broad trade-weighted USD index",
    }


def test_quote_dxy_returns_unavailable_when_provider_error():
    spec = make_quote_dxy_tool(lambda s, n: {"status": "error", "error": "no api key"})
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_dxy", {})

    assert result.status == "ok"
    assert result.content["status"] == "unavailable"
    assert result.content["reason_code"] == "provider_unavailable"


def test_quote_dxy_returns_unavailable_when_empty_data():
    spec = make_quote_dxy_tool(lambda s, n: {"status": "ok", "data": []})
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_dxy", {})

    assert result.status == "ok"
    assert result.content["status"] == "unavailable"
    assert result.content["reason_code"] == "no_observations"


def test_quote_dxy_returns_unavailable_when_malformed():
    spec = make_quote_dxy_tool(lambda s, n: "not a dict")
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_dxy", {})

    assert result.status == "ok"
    assert result.content["status"] == "unavailable"
    assert result.content["reason_code"] == "malformed_provider_response"


def test_quote_dxy_wraps_provider_exception_as_tool_error():
    def boom(series_id, limit):
        raise RuntimeError("network unreachable")

    spec = make_quote_dxy_tool(boom)
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_dxy", {})

    assert result.status == "error"
    assert result.error_code == "fred_provider_error"
    assert "network unreachable" not in (result.error_message or "")  # type name only


def test_quote_dxy_rejects_unexpected_args():
    spec = make_quote_dxy_tool(lambda s, n: {"status": "ok", "data": []})
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("quote_dxy", {"date": "today"})

    assert result.status == "error"
    assert result.error_code == "unexpected_args"


# -- finalize_macro_brief -------------------------------------------------


def test_finalize_macro_brief_returns_brief_payload():
    spec = make_finalize_macro_brief_tool()
    registry = AgentToolRegistry()
    registry.register(spec)

    brief = {"core_conclusion": "balanced", "module_table": [], "scenarios": {}}
    result = registry.dispatch("finalize_macro_brief", {"brief": brief})

    assert result.status == "ok"
    assert result.content == {"finalized": True, "brief": brief}


def test_finalize_macro_brief_name_constant():
    assert FINALIZE_TOOL_NAME == "finalize_macro_brief"


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"brief": "not a dict"},
        {"brief": None},
        {"brief": ["list", "instead"]},
    ],
)
def test_finalize_macro_brief_rejects_non_object_brief(args):
    spec = make_finalize_macro_brief_tool()
    registry = AgentToolRegistry()
    registry.register(spec)

    result = registry.dispatch("finalize_macro_brief", args)

    assert result.status == "error"
    assert result.error_code == "invalid_brief"


# -- bundle ---------------------------------------------------------------


def test_build_f1_portfolio_tools_registers_all_three():
    bundle = build_f1_portfolio_tools(
        portfolio_snapshot_fn=lambda: _full_portfolio_snapshot(),
        fred_series_fn=lambda s, n: {"status": "ok", "data": []},
    )
    registry = AgentToolRegistry()
    bundle.register_all(registry)

    assert sorted(registry.names()) == [
        "finalize_macro_brief",
        "portfolio_overlay",
        "quote_dxy",
    ]


def test_all_f1_bundles_combined_have_11_tools():
    """F1 ships exactly 11 tools (5 read-only + 3 network + 3 portfolio/dxy/finalize)."""
    read_only = build_f1_read_only_tools(
        summary_fn=lambda: {},
        evidence_fn=lambda: {"modules": []},
        quote_fn=lambda symbols: [],
        curve_fn=lambda: {},
        next_releases_fn=lambda window: [],
        events_by_name_fn=lambda name, limit: [],
    )
    network = build_f1_network_tools(
        search_execute_fn=lambda req: SearchResponse(results=[], search_available=False, guard_passed=False),
        rag_retrieve_fn=lambda q, **kw: [],
        commodity_quote_fn=lambda b: {"benchmark": b, "status": "unavailable",
                                      "reason_code": "search_unavailable"},
    )
    portfolio = build_f1_portfolio_tools(
        portfolio_snapshot_fn=lambda: {},
        fred_series_fn=lambda s, n: {"status": "ok", "data": []},
    )

    registry = AgentToolRegistry()
    read_only.register_all(registry)
    network.register_all(registry)
    portfolio.register_all(registry)

    assert len(registry.names()) == 11
    assert FINALIZE_TOOL_NAME in registry.names()


# ---------------------------------------------------------------------------
# F1-4 dispatch-level redaction + size cap
# ---------------------------------------------------------------------------


def _registry_with(handler, name: str = "t") -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name=name,
            description="leak test",
            parameters_schema={"type": "object", "properties": {}, "required": []},
            handler=handler,
        )
    )
    return registry


@pytest.mark.parametrize(
    "raw, must_contain, must_not_contain",
    [
        # Tavily key (used by transport)
        (
            {"note": "Authorization: Bearer tvly-Abc1234567890XYZ"},
            ["REDACTED"],
            ["tvly-Abc1234567890XYZ"],
        ),
        # OpenAI-style key
        (
            {"leak": "sk-1234567890abcdefGHIJ"},
            ["[REDACTED_API_KEY]"],
            ["sk-1234567890abcdefGHIJ"],
        ),
        # Bearer token alone
        (
            {"h": "Bearer eyJhbGciOiJIUzI1NiJ9"},
            ["Bearer [REDACTED]"],
            ["eyJhbGciOiJIUzI1NiJ9"],
        ),
        # SHA-256 hex (governance content_sha256)
        (
            {"hash": "a" * 64},
            ["[REDACTED_SHA256]"],
            ["a" * 64],
        ),
        # Unix path
        (
            {"path": "/Users/alice/holdings.csv"},
            ["[REDACTED_PATH]"],
            ["/Users/alice/holdings.csv"],
        ),
        # Linux home path
        (
            {"path": "/home/sekio/secrets.env"},
            ["[REDACTED_PATH]"],
            ["/home/sekio/secrets.env"],
        ),
        # Windows path
        (
            {"path": "C:\\Users\\bob\\data.txt"},
            ["[REDACTED_PATH]"],
            ["bob\\data.txt"],
        ),
        # /mnt/data
        (
            {"x": "see /mnt/data/x.parquet for raw"},
            ["[REDACTED_PATH]"],
            ["/mnt/data/x.parquet"],
        ),
    ],
)
def test_dispatch_redacts_secrets_in_content(raw, must_contain, must_not_contain):
    import json as _json

    registry = _registry_with(lambda args: raw)
    result = registry.dispatch("t", {})

    serialized = _json.dumps(result.content)
    for marker in must_contain:
        assert marker in serialized
    for leak in must_not_contain:
        assert leak not in serialized


def test_dispatch_redacts_in_nested_structures():
    import json as _json

    nested = {
        "outer": {
            "list": [
                {"key": "tvly-abc1234567890"},
                "Authorization: Bearer secret-token-xyz-12345",
            ],
            "tuple_field": ("api_key=hidden123XYZ987abc", "ok"),
        }
    }
    registry = _registry_with(lambda args: nested)
    result = registry.dispatch("t", {})

    serialized = _json.dumps(result.content)
    assert "tvly-abc1234567890" not in serialized
    assert "secret-token-xyz-12345" not in serialized
    assert "hidden123XYZ987abc" not in serialized


def test_dispatch_url_fields_exempt_from_path_redactor_but_keys_still_stripped():
    """A real source_url contains /something/ which would normally trigger
    the path redactor. URL-like keys are exempt for that pattern, but
    api_key= / bearer / sha256 patterns still apply even inside URLs."""
    raw = {
        "source_url": "https://reuters.com/markets/yields",
        "leaky_url": "https://example.com?api_key=hidden123abcXYZ987",
    }
    registry = _registry_with(lambda args: raw)
    result = registry.dispatch("t", {})

    assert result.content["source_url"] == "https://reuters.com/markets/yields"
    assert "hidden123abcXYZ987" not in result.content["leaky_url"]


def test_dispatch_error_message_is_redacted():
    def boom(_args):
        raise RuntimeError("connect failed using tvly-Secret1234567890")

    registry = _registry_with(boom)
    result = registry.dispatch("t", {})

    assert result.status == "error"
    assert "tvly-Secret1234567890" not in (result.error_message or "")
    assert "REDACTED" in (result.error_message or "")


def test_dispatch_size_cap_replaces_oversized_content_with_marker():
    big = {"blob": "x" * (TOOL_RESULT_MAX_CHARS + 1000)}
    registry = _registry_with(lambda args: big)
    result = registry.dispatch("t", {})

    assert result.status == "ok"
    assert isinstance(result.content, dict)
    assert result.content.get("truncated") is True
    assert result.content["original_size_chars"] > TOOL_RESULT_MAX_CHARS
    assert result.content["max_chars"] == TOOL_RESULT_MAX_CHARS
    assert isinstance(result.content["preview"], str)
    assert len(result.content["preview"]) <= 2000


def test_dispatch_small_content_unaffected_by_size_cap():
    small = {"value": "y" * 100}
    registry = _registry_with(lambda args: small)
    result = registry.dispatch("t", {})

    assert result.status == "ok"
    assert result.content == small


def test_dispatch_size_cap_after_redaction_keeps_preview_safe():
    """Redaction runs BEFORE the cap, so even the preview slice in a
    truncation marker must never contain raw secrets."""
    payload = {"head": "tvly-veryLongSecret1234567890" + ("z" * 9000)}
    registry = _registry_with(lambda args: payload)
    result = registry.dispatch("t", {})

    assert result.content.get("truncated") is True
    assert "tvly-veryLongSecret1234567890" not in result.content["preview"]


def test_dispatch_non_serializable_still_rejected():
    """The F1-4 path must not weaken the original non-JSON guard."""
    registry = _registry_with(lambda args: {"x": {1, 2, 3}})
    result = registry.dispatch("t", {})
    assert result.status == "error"
    assert result.error_code == "non_serializable_result"
