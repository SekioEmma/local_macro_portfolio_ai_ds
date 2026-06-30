"""Phase F agent tool registry.

Defines tool specs (OpenAI function-calling JSON schema) and synchronous
handlers that wrap existing services. The registry is the only place
where Phase F agent dispatches tool calls. It produces JSON-serializable
results suitable for being fed back to the LLM.

This module:
- defines `ToolSpec`, `ToolResult`, `AgentToolRegistry`
- registers F1-1's 5 read-only tools: dashboard_query, evidence_lookup,
  quote_etf, treasury_curve, calendar_lookup
- F1-2 adds search_tavily, rag_retrieve, commodity_quote
- F1-3 adds portfolio_overlay, quote_dxy, finalize_macro_brief
- F1-4 applies centralized redaction + 8 KB size cap inside dispatch so
  no handler can bypass them; the same redaction is applied to error
  messages before they reach the LLM.

It does NOT:
- call any LLM
- read secrets / env / network directly
- persist anything to disk
- mutate any external state
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal


# ---------------------------------------------------------------------------
# F1-4 redaction + size cap (applied in AgentToolRegistry.dispatch)
# ---------------------------------------------------------------------------

# 8 KB cap on the serialized JSON payload (chars ~ bytes for ASCII / few
# multi-byte chars). Matches the plan's 8000-char per-tool-call budget.
TOOL_RESULT_MAX_CHARS = 8192
_TRUNCATION_PREVIEW_CHARS = 2000
ToolBudgetClass = Literal[
    "local_read",
    "rag_retrieval",
    "external_search",
    "external_quote",
    "provider_call",
    "finalize",
]

# Patterns that must never reach the LLM:
#  - common API key prefixes / shapes
#  - HTTP Authorization / Bearer tokens
#  - SHA-256-like (64 hex chars) — used for content hashes in governance
#  - local filesystem paths (Windows / *nix / mnt)
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Token-shape secrets — bounded length so the regex does NOT greedily
    # eat trailing payload bytes that happen to share the character class.
    (re.compile(r"(?i)\btvly-[A-Za-z0-9_-]{8,128}"), "[REDACTED_TAVILY_KEY]"),
    (re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{16,128}"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-/+=]{8,512}"), "Bearer [REDACTED]"),
    (
        re.compile(r"(?i)\bAuthorization\s*:\s*[A-Za-z0-9._\-/+=\s]{8,512}"),
        "Authorization: [REDACTED]",
    ),
    (
        re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*[A-Za-z0-9._\-/+=]{8,256}"),
        "api_key=[REDACTED]",
    ),
    (re.compile(r"\b[0-9a-f]{64}\b"), "[REDACTED_SHA256]"),
    (re.compile(r"\b[A-Z]:[\\/][^\s\"'<>]+"), "[REDACTED_PATH]"),
    (re.compile(r"/Users/[^\s\"'<>]+"), "[REDACTED_PATH]"),
    (re.compile(r"/home/[^\s\"'<>]+"), "[REDACTED_PATH]"),
    (re.compile(r"/mnt/data[^\s\"'<>]*"), "[REDACTED_PATH]"),
)

# Source/url fields that legitimately contain URLs (and may include path
# segments that look like /home/<segment>). These keys' string values are
# exempt from the local-path redactor — but ALL other redactions still apply.
_URL_LIKE_KEYS = frozenset({"url", "source_url", "canonical_url", "endpoint", "href"})


def _redact_string(value: str, *, is_url_field: bool = False) -> str:
    out = value
    for pattern, replacement in _REDACTION_PATTERNS:
        # Path redactor exemption for url-like fields. Other patterns still
        # apply — a URL containing an api_key= still gets the key stripped.
        if is_url_field and replacement == "[REDACTED_PATH]":
            continue
        out = pattern.sub(replacement, out)
    return out


def _redact(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, str):
        return _redact_string(value, is_url_field=parent_key in _URL_LIKE_KEYS)
    if isinstance(value, dict):
        return {k: _redact(v, parent_key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, parent_key=parent_key) for item in value]
    return value


def _enforce_size_cap(content: Any, max_chars: int = TOOL_RESULT_MAX_CHARS) -> Any:
    """Cap the serialized JSON payload size.

    If the JSON exceeds ``max_chars`` chars, the content is replaced with a
    structured truncation marker. We never silently truncate a JSON string
    mid-encoding (which would produce invalid JSON downstream).
    """
    try:
        serialized = json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return content
    if len(serialized) <= max_chars:
        return content
    return {
        "truncated": True,
        "original_size_chars": len(serialized),
        "max_chars": max_chars,
        "preview": serialized[:_TRUNCATION_PREVIEW_CHARS],
    }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    budget_class: ToolBudgetClass | None = None

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
        if spec.budget_class is None:
            spec = replace(spec, budget_class=_infer_budget_class(spec.name))
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
            return _redacted_error("unknown_tool", f"tool not registered: {name}")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return _redacted_error(
                "invalid_args_type", f"args must be dict, got {type(args).__name__}"
            )
        try:
            result = spec.handler(args)
        except _ToolValidationError as exc:
            return _redacted_error(exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001 — handler exceptions become tool errors
            return _redacted_error("handler_exception", f"{type(exc).__name__}: {exc}")

        if not _is_json_serializable(result):
            return _redacted_error(
                "non_serializable_result",
                f"handler returned non-JSON value of type {type(result).__name__}",
            )

        # F1-4: redact secrets / paths / sha256 before sizing — redaction
        # may grow the payload (replacements like `[REDACTED_PATH]` are
        # short, so growth is bounded), but it must happen BEFORE the cap
        # so the LLM never sees a truncated preview that still contains
        # raw secrets in the first 2000 chars.
        redacted = _redact(result)
        capped = _enforce_size_cap(redacted)
        return ToolResult(status="ok", content=capped)


def _redacted_error(code: str, message: str) -> "ToolResult":
    return ToolResult(
        status="error",
        error_code=code,
        error_message=_redact_string(message),
    )


def _infer_budget_class(tool_name: str) -> ToolBudgetClass:
    if tool_name == "rag_retrieve":
        return "rag_retrieval"
    if tool_name in {"search_tavily", "commodity_quote"}:
        return "external_search"
    if tool_name in {"quote_etf", "treasury_curve", "quote_dxy"}:
        return "external_quote"
    if tool_name == FINALIZE_TOOL_NAME:
        return "finalize"
    return "local_read"


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


# ---------------------------------------------------------------------------
# F1-2 tool handlers (guarded network / retrieval)
#
# Every network-touching handler accepts an injected callable so tests use
# fakes. The agent's act of invoking these tools is itself the explicit
# user-approved request (parent `/api/agent/run` was user-triggered), so
# `confirm_external_search` is fixed True for search_tavily and
# `include_local_only` is fixed False for rag_retrieve. Neither flag is
# exposed in the LLM-facing parameter schema; the LLM cannot weaken or
# relax the guarded request shape.
# ---------------------------------------------------------------------------

# Forward-only function signatures so this module never imports the heavy
# downstream services at module load.
SearchExecuteFn = Callable[[Any], Any]  # TavilySearchApiRequest -> SearchResponse
RagRetrieveFn = Callable[..., Any]  # query, top_k, doc_type_filter, include_local_only -> list
CommodityQuoteFn = Callable[[str], Any]  # benchmark -> CommodityQuoteSnapshot

_COMMODITY_BENCHMARKS = frozenset({"brent", "wti"})


def make_search_tavily_tool(execute_fn: SearchExecuteFn) -> ToolSpec:
    """Wrap TavilySearchExecutionService.execute as an agent tool.

    Forces `confirm_external_search=True` because the agent run is itself
    the explicit user request. The execution service still enforces every
    other gate (sanitizer, runtime policy, allowlist, budget, response
    guard) and fails closed on any failure.

    F1-5: every result is scored by ``MacroNewsRelevanceFilter`` and
    results below the fixed threshold are dropped from the LLM-facing
    payload. The threshold is not exposed in the LLM-facing schema so the
    model cannot lower it.
    """

    from app_backend.schemas.search_external import TavilySearchApiRequest
    from app_backend.services.macro_news_relevance_filter import (
        DEFAULT_RELEVANCE_THRESHOLD,
        filter_results,
    )

    def handler(args: dict[str, Any]) -> Any:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise _ToolValidationError("invalid_query", "query must be a non-empty string")
        if len(query) > 500:
            raise _ToolValidationError("invalid_query", "query must be ≤ 500 chars")

        max_results = args.get("max_results", 5)
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise _ToolValidationError("invalid_max_results", "max_results must be int")
        if not 1 <= max_results <= 20:
            raise _ToolValidationError("invalid_max_results", "max_results must be 1..20")

        domain_filter = args.get("domain_filter") or []
        if not isinstance(domain_filter, list) or not all(
            isinstance(d, str) and d.strip() for d in domain_filter
        ):
            raise _ToolValidationError(
                "invalid_domain_filter",
                "domain_filter must be a list of non-empty strings (or omitted)",
            )

        request = TavilySearchApiRequest(
            query=query,
            max_results=max_results,
            domain_filter=list(domain_filter),
            confirm_external_search=True,
        )
        response = execute_fn(request)
        payload = _to_jsonable(response)
        # Strip provider error / blocking flag detail before handing back
        # to the LLM. The guarded service already redacts upstream, but the
        # tool layer makes the contract explicit.
        if not isinstance(payload, dict):
            return {
                "results": [],
                "search_available": False,
                "guard_passed": False,
                "result_count": 0,
                "filtered_low_relevance_count": 0,
                "relevance_threshold": DEFAULT_RELEVANCE_THRESHOLD,
            }

        raw_results = payload.get("results") or []
        if not isinstance(raw_results, list):
            raw_results = []
        kept, dropped = filter_results(raw_results, threshold=DEFAULT_RELEVANCE_THRESHOLD)
        scored = [
            {
                "url": item.url,
                "title": item.title,
                "snippet": item.snippet,
                "domain": item.domain,
                "relevance_score": item.score,
                **({"published_at": item.published_at} if item.published_at else {}),
            }
            for item in kept
        ]
        return {
            "results": scored,
            "search_available": bool(payload.get("search_available")),
            "guard_passed": bool(payload.get("guard_passed")),
            "result_count": len(scored),
            "filtered_low_relevance_count": dropped,
            "relevance_threshold": DEFAULT_RELEVANCE_THRESHOLD,
        }

    return ToolSpec(
        name="search_tavily",
        description=(
            "Search the curated external macro-news corpus via Tavily "
            "(reuters.com, bloomberg.com, federalreserve.gov, bls.gov, "
            "bea.gov, fred.stlouisfed.org, wsj.com, ft.com, imf.org, "
            "worldbank.org, bis.org). Fail-closed by default. Use only "
            "when local sources (dashboard, evidence, rag_retrieve) cannot "
            "answer the question."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                    "description": "Search query in plain English",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                    "description": "Maximum number of results to return",
                },
                "domain_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional narrowing to specific allowlisted domains. "
                        "Out-of-allowlist domains fail-closed."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def make_rag_retrieve_tool(retrieve_fn: RagRetrieveFn) -> ToolSpec:
    """Wrap RAGRetrievalService.retrieve as an agent tool.

    Forces `include_local_only=False` so the LLM never sees local-only
    documents. Returns chunk text along with title / doc_type / domain so
    the LLM can build a source attribution.
    """

    def handler(args: dict[str, Any]) -> Any:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise _ToolValidationError("invalid_query", "query must be a non-empty string")
        if len(query) > 500:
            raise _ToolValidationError("invalid_query", "query must be ≤ 500 chars")

        top_k = args.get("top_k", 5)
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise _ToolValidationError("invalid_top_k", "top_k must be int")
        if not 1 <= top_k <= 20:
            raise _ToolValidationError("invalid_top_k", "top_k must be 1..20")

        doc_type = args.get("doc_type")
        if doc_type is not None and not isinstance(doc_type, str):
            raise _ToolValidationError("invalid_doc_type", "doc_type must be str or null")

        chunks = retrieve_fn(
            query,
            top_k=top_k,
            doc_type_filter=doc_type or None,
            include_local_only=False,
        )
        rendered: list[dict[str, Any]] = []
        for chunk in chunks or []:
            item = _to_jsonable(chunk)
            if isinstance(item, dict):
                # Drop the local-only flag from the LLM-facing payload — it
                # is always False here (handler enforced) and contributes
                # nothing to the model.
                item.pop("external_llm_context_allowed", None)
                rendered.append(item)
        return {"chunks": rendered, "chunk_count": len(rendered)}

    return ToolSpec(
        name="rag_retrieve",
        description=(
            "Retrieve relevant text passages from the local knowledge base "
            "(curated Federal Reserve / BLS / BEA / institutional research). "
            "Uses hybrid vector + keyword retrieval. Prefer this over "
            "search_tavily for historical context, FOMC statements, and "
            "official publications."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                    "description": "Search query in plain English",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                    "description": "Maximum number of chunks to return",
                },
                "doc_type": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional doc_type filter (e.g. 'policy_doc', "
                        "'research_report'). Omit for any."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def make_commodity_quote_tool(quote_fn: CommodityQuoteFn) -> ToolSpec:
    """Wrap CommodityQuoteService.quote (Brent / WTI only).

    The commodity service itself routes through the same guarded search
    execution and the fixed three-domain allowlist (reuters / bloomberg /
    oilprice). Tool layer pre-validates benchmark so a typo fails fast
    with a stable error_code rather than burning a search call.
    """

    def handler(args: dict[str, Any]) -> Any:
        benchmark = args.get("benchmark")
        if not isinstance(benchmark, str) or not benchmark.strip():
            raise _ToolValidationError("invalid_benchmark", "benchmark must be a string")
        normalized = benchmark.strip().lower()
        if normalized not in _COMMODITY_BENCHMARKS:
            raise _ToolValidationError(
                "invalid_benchmark",
                f"benchmark must be one of {sorted(_COMMODITY_BENCHMARKS)}",
            )
        return _to_jsonable(quote_fn(normalized))

    return ToolSpec(
        name="commodity_quote",
        description=(
            "Return a guarded snapshot of the latest Brent or WTI crude oil "
            "price per barrel, sourced from reuters.com / bloomberg.com / "
            "oilprice.com. Returns 'unavailable' fail-closed when search is "
            "disabled, budget exhausted, or no strict match found."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "benchmark": {
                    "type": "string",
                    "enum": ["brent", "wti"],
                    "description": "Which crude benchmark to quote",
                },
            },
            "required": ["benchmark"],
            "additionalProperties": False,
        },
        handler=handler,
    )


@dataclass
class F1NetworkTools:
    """Bundle of F1-2 guarded network / retrieval tool specs."""

    search_tavily: ToolSpec
    rag_retrieve: ToolSpec
    commodity_quote: ToolSpec

    def register_all(self, registry: AgentToolRegistry) -> None:
        registry.register(self.search_tavily)
        registry.register(self.rag_retrieve)
        registry.register(self.commodity_quote)


def build_f1_network_tools(
    *,
    search_execute_fn: SearchExecuteFn,
    rag_retrieve_fn: RagRetrieveFn,
    commodity_quote_fn: CommodityQuoteFn,
) -> F1NetworkTools:
    return F1NetworkTools(
        search_tavily=make_search_tavily_tool(search_execute_fn),
        rag_retrieve=make_rag_retrieve_tool(rag_retrieve_fn),
        commodity_quote=make_commodity_quote_tool(commodity_quote_fn),
    )


# ---------------------------------------------------------------------------
# F1-3 tool handlers (portfolio / DXY / finalize)
#
# `portfolio_overlay` strictly never exposes raw dollar amounts, per-holding
# details, account names, transaction history, or cost basis to the LLM via
# the tool channel. The Phase F Holdings Injection Exception in CLAUDE.md
# governs a SEPARATE channel (the system prompt) which is handled in F3 and
# is the only authorized place where real amounts may reach the model.
#
# `quote_dxy` reads FRED DTWEXBGS through an injected fred_series callable
# so the tool layer never imports a network client and tests use fakes.
#
# `finalize_macro_brief` is a terminator: the agent runtime detects this
# tool name and exits the loop. At F1 the handler only normalizes the
# brief into a dict; F2 will add full schema validation.
# ---------------------------------------------------------------------------

# Function signatures kept fully forward so this module never imports the
# heavy downstream services at module load.
PortfolioSnapshotFn = Callable[[], Any]  # () -> dict-like full snapshot
FredSeriesFn = Callable[[str, int], Any]  # (series_id, limit) -> dict

# Fields lifted from portfolio_engine.generate_portfolio_snapshot output that
# are safe to expose to the LLM. Any other field — and especially raw dollar
# amounts, per-holding details, total_profit_loss, dca_*, account names — is
# dropped before the tool result is returned.
_PORTFOLIO_SAFE_FIELDS: tuple[str, ...] = (
    "weights_ex_cash",
    "target_allocation",
    "deviation",
    "deviation_flags",
    "holdings_freshness_status",
    "holdings_age_days",
    "holdings_updated_at_status",
    "holdings_row_count",
)


def make_portfolio_overlay_tool(snapshot_fn: PortfolioSnapshotFn) -> ToolSpec:
    """Wrap portfolio_engine snapshot as a sanitized overlay tool.

    Returns ONLY the deviation summary: weights, target allocation,
    deviation per asset class, and freshness status. Dollar amounts,
    per-holding lots, account names, cost basis, P/L, and the DCA plan
    are dropped before reaching the LLM. The Phase F Holdings Injection
    Exception (system-prompt channel) is unrelated and handled in F3.
    """

    def handler(args: dict[str, Any]) -> Any:
        if args:
            raise _ToolValidationError(
                "unexpected_args", "portfolio_overlay takes no parameters"
            )
        raw = snapshot_fn()
        snapshot = _to_jsonable(raw)
        if not isinstance(snapshot, dict):
            return {"available": False, "reason": "portfolio_snapshot_unavailable"}
        return _redact_portfolio_snapshot(snapshot)

    return ToolSpec(
        name="portfolio_overlay",
        description=(
            "Return a sanitized portfolio overlay summary: current asset-class "
            "weights, target allocation, per-class deviation, deviation flags, "
            "and holdings freshness. No dollar amounts, no per-position lots, "
            "no account names, no cost basis. Use this to decide whether the "
            "asset-class mix is on or off target."
        ),
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _redact_portfolio_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    overlay: dict[str, Any] = {
        key: snapshot[key] for key in _PORTFOLIO_SAFE_FIELDS if key in snapshot
    }
    overlay["available"] = bool(overlay.get("weights_ex_cash") or overlay.get("target_allocation"))
    return overlay


def make_quote_dxy_tool(fred_series_fn: FredSeriesFn) -> ToolSpec:
    """Wrap FRED DTWEXBGS as a DXY-equivalent quote tool.

    DTWEXBGS is the broad trade-weighted USD index (daily). Returns the
    most recent valid observation; falls back to 'unavailable' when the
    provider call fails or returns malformed data. The fred_series_fn
    callable is injected so tests never make a real network call.
    """

    def handler(args: dict[str, Any]) -> Any:
        if args:
            raise _ToolValidationError("unexpected_args", "quote_dxy takes no parameters")
        try:
            payload = fred_series_fn("DTWEXBGS", 10)
        except Exception as exc:  # noqa: BLE001 — handler maps to error result
            raise _ToolValidationError(
                "fred_provider_error",
                f"DXY (DTWEXBGS) provider call failed: {type(exc).__name__}",
            ) from exc
        return _shape_dxy_quote(payload)

    return ToolSpec(
        name="quote_dxy",
        description=(
            "Return the latest broad trade-weighted US dollar index "
            "(FRED series DTWEXBGS, daily). Use as a DXY proxy for "
            "macro USD strength analysis. No network call if the FRED "
            "provider is unavailable; returns status='unavailable' "
            "fail-closed."
        ),
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _shape_dxy_quote(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "unavailable", "reason_code": "malformed_provider_response"}
    if payload.get("status") != "ok":
        return {
            "status": "unavailable",
            "reason_code": "provider_unavailable",
            "series_id": "DTWEXBGS",
        }
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return {
            "status": "unavailable",
            "reason_code": "no_observations",
            "series_id": "DTWEXBGS",
        }
    latest = data[0]
    if not isinstance(latest, dict):
        return {
            "status": "unavailable",
            "reason_code": "malformed_provider_response",
            "series_id": "DTWEXBGS",
        }
    return {
        "status": "ok",
        "series_id": "DTWEXBGS",
        "value": latest.get("value"),
        "observation_date": latest.get("date"),
        "source": "FRED",
        "name": "broad trade-weighted USD index",
    }


def make_finalize_macro_brief_tool() -> ToolSpec:
    """Terminator tool used by the agent runtime to exit the dispatch loop.

    The handler does not validate the brief against the full MacroBrief
    Pydantic schema — that is F2's job; F5 will catch the tool name and
    drive the brief through the parser. F1 only enforces that the brief
    argument is a JSON object.
    """

    def handler(args: dict[str, Any]) -> Any:
        brief = args.get("brief")
        if not isinstance(brief, dict):
            raise _ToolValidationError(
                "invalid_brief", "brief must be a JSON object (10-section MacroBrief)"
            )
        return {"finalized": True, "brief": brief}

    return ToolSpec(
        name="finalize_macro_brief",
        description=(
            "Submit the final 10-section MacroBrief. Calling this tool is "
            "the ONLY way to terminate the agent. Do not call this until "
            "you have collected enough evidence through other tools to fill "
            "every section."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "brief": {
                    "type": "object",
                    "description": "The full MacroBrief JSON object (10 sections).",
                },
            },
            "required": ["brief"],
            "additionalProperties": False,
        },
        handler=handler,
    )


FINALIZE_TOOL_NAME = "finalize_macro_brief"


@dataclass
class F1PortfolioTools:
    """Bundle of F1-3 portfolio / DXY / finalize tool specs."""

    portfolio_overlay: ToolSpec
    quote_dxy: ToolSpec
    finalize_macro_brief: ToolSpec

    def register_all(self, registry: AgentToolRegistry) -> None:
        registry.register(self.portfolio_overlay)
        registry.register(self.quote_dxy)
        registry.register(self.finalize_macro_brief)


def build_f1_portfolio_tools(
    *,
    portfolio_snapshot_fn: PortfolioSnapshotFn,
    fred_series_fn: FredSeriesFn,
) -> F1PortfolioTools:
    return F1PortfolioTools(
        portfolio_overlay=make_portfolio_overlay_tool(portfolio_snapshot_fn),
        quote_dxy=make_quote_dxy_tool(fred_series_fn),
        finalize_macro_brief=make_finalize_macro_brief_tool(),
    )


__all__ = [
    "AgentToolRegistry",
    "F1NetworkTools",
    "F1PortfolioTools",
    "F1ReadOnlyTools",
    "FINALIZE_TOOL_NAME",
    "TOOL_RESULT_MAX_CHARS",
    "ToolResult",
    "ToolSpec",
    "build_f1_network_tools",
    "build_f1_portfolio_tools",
    "build_f1_read_only_tools",
    "make_calendar_lookup_tool",
    "make_commodity_quote_tool",
    "make_dashboard_query_tool",
    "make_evidence_lookup_tool",
    "make_finalize_macro_brief_tool",
    "make_portfolio_overlay_tool",
    "make_quote_dxy_tool",
    "make_quote_etf_tool",
    "make_rag_retrieve_tool",
    "make_search_tavily_tool",
    "make_treasury_curve_tool",
]
