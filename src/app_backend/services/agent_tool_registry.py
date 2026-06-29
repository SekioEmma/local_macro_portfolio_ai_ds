"""Phase F agent tool registry.

Defines tool specs (OpenAI function-calling JSON schema) and synchronous
handlers that wrap existing services. The registry is the only place
where Phase F agent dispatches tool calls. It produces JSON-serializable
results suitable for being fed back to the LLM.

This module:
- defines `ToolSpec`, `ToolResult`, `AgentToolRegistry`
- registers F1-1's 5 read-only tools: dashboard_query, evidence_lookup,
  quote_etf, treasury_curve, calendar_lookup
- F1-2/F1-3 add the remaining tools (search_tavily, rag_retrieve,
  commodity_quote, portfolio_overlay, quote_dxy, finalize_macro_brief)
- F1-4 adds result redaction + size cap

It does NOT:
- call any LLM
- read secrets / env / network directly
- persist anything to disk
- mutate any external state
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


@dataclass(frozen=True)
class ToolResult:
    status: str
    content: Any = None
    error_code: str | None = None
    error_message: str | None = None

    def to_json_payload(self) -> dict[str, Any]:
        if self.status == "ok":
            return {"status": "ok", "content": self.content}
        return {
            "status": "error",
            "error_code": self.error_code or "unknown_error",
            "error_message": self.error_message or "",
        }


class AgentToolRegistry:
    """In-process registry of agent tool specs.

    `dispatch(name, args)` runs the registered handler and wraps every
    outcome (success or exception) into a `ToolResult`. Handlers must
    return JSON-serializable values; non-serializable returns raise
    `error_code='non_serializable_result'`.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._specs.keys())

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def openai_schema(self) -> list[dict[str, Any]]:
        return [self._specs[name].to_openai_schema() for name in self.names()]

    def dispatch(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            return ToolResult(
                status="error",
                error_code="unknown_tool",
                error_message=f"tool not registered: {name}",
            )
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return ToolResult(
                status="error",
                error_code="invalid_args_type",
                error_message=f"args must be dict, got {type(args).__name__}",
            )
        try:
            result = spec.handler(args)
        except _ToolValidationError as exc:
            return ToolResult(
                status="error",
                error_code=exc.code,
                error_message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 — handler exceptions become tool errors
            return ToolResult(
                status="error",
                error_code="handler_exception",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        if not _is_json_serializable(result):
            return ToolResult(
                status="error",
                error_code="non_serializable_result",
                error_message=f"handler returned non-JSON value of type {type(result).__name__}",
            )
        return ToolResult(status="ok", content=result)


class _ToolValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_json_serializable(value: Any) -> bool:
    import json
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


# ---------------------------------------------------------------------------
# F1-1 tool handlers (read-only, no network)
# ---------------------------------------------------------------------------

# Dependency-injection points: each handler factory accepts the underlying
# service callable so tests can inject fakes without touching real I/O.

DashboardSummaryFn = Callable[[], Any]
DashboardEvidenceFn = Callable[[], Any]
QuoteEtfFn = Callable[[list[str]], Any]
TreasuryCurveFn = Callable[[], Any]
CalendarNextReleasesFn = Callable[[int], Any]
CalendarByNameFn = Callable[[str, int], Any]


def _to_jsonable(value: Any) -> Any:
    """Recursively coerce pydantic models / dataclasses / common types into
    JSON-serializable dict / list / scalars.

    Pydantic v2: model_dump(mode='json') already returns JSON-safe forms.
    """
    from dataclasses import asdict, is_dataclass

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def make_dashboard_query_tool(summary_fn: DashboardSummaryFn) -> ToolSpec:
    def handler(args: dict[str, Any]) -> Any:
        if args:
            raise _ToolValidationError("unexpected_args", "dashboard_query takes no parameters")
        return _to_jsonable(summary_fn())

    return ToolSpec(
        name="dashboard_query",
        description=(
            "Return the current local macro dashboard summary (module statuses, "
            "counts, freshness). No parameters. Reads only the latest local "
            "reports; no network call."
        ),
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=handler,
    )


def make_evidence_lookup_tool(evidence_fn: DashboardEvidenceFn) -> ToolSpec:
    def handler(args: dict[str, Any]) -> Any:
        module_key = args.get("module_key")
        metric_key = args.get("metric_key")
        if module_key is not None and not isinstance(module_key, str):
            raise _ToolValidationError("invalid_module_key", "module_key must be str or null")
        if metric_key is not None and not isinstance(metric_key, str):
            raise _ToolValidationError("invalid_metric_key", "metric_key must be str or null")

        evidence = _to_jsonable(evidence_fn())
        rows = _extract_evidence_rows(evidence)
        if module_key:
            rows = [row for row in rows if row.get("module_key") == module_key]
        if metric_key:
            rows = [row for row in rows if row.get("metric_key") == metric_key]
        return {"rows": rows, "row_count": len(rows)}

    return ToolSpec(
        name="evidence_lookup",
        description=(
            "Return rows from the local dashboard evidence table. Optionally "
            "filter by module_key (e.g. 'rate_pressure', 'inflation_energy_pressure') "
            "and/or metric_key (e.g. 'dgs10', 'core_pce_yoy'). No parameters returns "
            "all rows. No network call."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "module_key": {
                    "type": ["string", "null"],
                    "description": "Optional module key to filter by",
                },
                "metric_key": {
                    "type": ["string", "null"],
                    "description": "Optional metric key to filter by",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _extract_evidence_rows(evidence_payload: Any) -> list[dict[str, Any]]:
    if isinstance(evidence_payload, dict):
        modules = evidence_payload.get("modules")
        if isinstance(modules, list):
            rows: list[dict[str, Any]] = []
            for module in modules:
                if not isinstance(module, dict):
                    continue
                module_key = module.get("module_key")
                for row in module.get("rows", []) or []:
                    if isinstance(row, dict):
                        merged = dict(row)
                        merged.setdefault("module_key", module_key)
                        rows.append(merged)
            return rows
        if "rows" in evidence_payload and isinstance(evidence_payload["rows"], list):
            return [row for row in evidence_payload["rows"] if isinstance(row, dict)]
    return []


_VALID_ETF_SYMBOLS = frozenset({"SPY", "QQQ", "SHY", "TLT", "GLD", "USO", "DXY"})


def make_quote_etf_tool(quote_fn: QuoteEtfFn) -> ToolSpec:
    def handler(args: dict[str, Any]) -> Any:
        symbols = args.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            raise _ToolValidationError("invalid_symbols", "symbols must be a non-empty list of strings")
        for symbol in symbols:
            if not isinstance(symbol, str) or not symbol.strip():
                raise _ToolValidationError("invalid_symbols", "each symbol must be a non-empty string")
        upper = [symbol.strip().upper() for symbol in symbols]
        unknown = [symbol for symbol in upper if symbol not in _VALID_ETF_SYMBOLS]
        if unknown:
            raise _ToolValidationError(
                "unknown_symbol",
                f"unsupported symbols: {unknown}; allowed: {sorted(_VALID_ETF_SYMBOLS)}",
            )
        return {"quotes": _to_jsonable(quote_fn(upper))}

    return ToolSpec(
        name="quote_etf",
        description=(
            "Return latest local ETF quote snapshots for the requested symbols. "
            "Symbols are case-insensitive. Allowed: SPY, QQQ, SHY, TLT, GLD, USO, DXY."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "ETF ticker symbols to quote",
                },
            },
            "required": ["symbols"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def make_treasury_curve_tool(curve_fn: TreasuryCurveFn) -> ToolSpec:
    def handler(args: dict[str, Any]) -> Any:
        if args:
            raise _ToolValidationError("unexpected_args", "treasury_curve takes no parameters")
        return _to_jsonable(curve_fn())

    return ToolSpec(
        name="treasury_curve",
        description=(
            "Return the latest local US Treasury yield curve snapshot "
            "(DGS3MO/2/5/10/30 etc.). No parameters. Read-only from local "
            "market_history; no network call."
        ),
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=handler,
    )


def make_calendar_lookup_tool(
    next_releases_fn: CalendarNextReleasesFn,
    events_by_name_fn: CalendarByNameFn,
) -> ToolSpec:
    def handler(args: dict[str, Any]) -> Any:
        event_name = args.get("event_name")
        window_days = args.get("window_days", 30)
        limit = args.get("limit", 5)

        if event_name is not None and not isinstance(event_name, str):
            raise _ToolValidationError("invalid_event_name", "event_name must be str or null")
        if not isinstance(window_days, int) or isinstance(window_days, bool):
            raise _ToolValidationError("invalid_window_days", "window_days must be int")
        if not 1 <= window_days <= 365:
            raise _ToolValidationError("invalid_window_days", "window_days must be 1..365")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise _ToolValidationError("invalid_limit", "limit must be int")
        if not 1 <= limit <= 100:
            raise _ToolValidationError("invalid_limit", "limit must be 1..100")

        if event_name:
            records = events_by_name_fn(event_name, limit)
            return {"events": _to_jsonable(records), "mode": "by_name"}
        records = next_releases_fn(window_days)
        return {"events": _to_jsonable(records), "mode": "next_releases", "window_days": window_days}

    return ToolSpec(
        name="calendar_lookup",
        description=(
            "Look up upcoming economic calendar events. Default: next 30 days of "
            "releases. Pass event_name (e.g. 'CPI', 'Employment Situation', 'PCE') "
            "to retrieve the most recent N occurrences of that event instead. "
            "No network call; reads local economic calendar database."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "event_name": {
                    "type": ["string", "null"],
                    "description": "Optional event name to filter by",
                },
                "window_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 365,
                    "default": 30,
                    "description": "Days ahead to look for next releases",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 5,
                    "description": "Maximum events to return when filtering by name",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=handler,
    )


@dataclass
class F1ReadOnlyTools:
    """Bundle of F1-1 read-only tool specs registered together."""

    dashboard_query: ToolSpec
    evidence_lookup: ToolSpec
    quote_etf: ToolSpec
    treasury_curve: ToolSpec
    calendar_lookup: ToolSpec

    def register_all(self, registry: AgentToolRegistry) -> None:
        registry.register(self.dashboard_query)
        registry.register(self.evidence_lookup)
        registry.register(self.quote_etf)
        registry.register(self.treasury_curve)
        registry.register(self.calendar_lookup)


def build_f1_read_only_tools(
    *,
    summary_fn: DashboardSummaryFn,
    evidence_fn: DashboardEvidenceFn,
    quote_fn: QuoteEtfFn,
    curve_fn: TreasuryCurveFn,
    next_releases_fn: CalendarNextReleasesFn,
    events_by_name_fn: CalendarByNameFn,
) -> F1ReadOnlyTools:
    return F1ReadOnlyTools(
        dashboard_query=make_dashboard_query_tool(summary_fn),
        evidence_lookup=make_evidence_lookup_tool(evidence_fn),
        quote_etf=make_quote_etf_tool(quote_fn),
        treasury_curve=make_treasury_curve_tool(curve_fn),
        calendar_lookup=make_calendar_lookup_tool(next_releases_fn, events_by_name_fn),
    )


__all__ = [
    "AgentToolRegistry",
    "F1ReadOnlyTools",
    "ToolResult",
    "ToolSpec",
    "build_f1_read_only_tools",
    "make_calendar_lookup_tool",
    "make_dashboard_query_tool",
    "make_evidence_lookup_tool",
    "make_quote_etf_tool",
    "make_treasury_curve_tool",
]
