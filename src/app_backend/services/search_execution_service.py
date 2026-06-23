from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, datetime, timezone

from app_backend.schemas.search_external import (
    SearchRequest,
    SearchResponse,
    SearchRuntimePolicy,
    TavilySearchApiRequest,
)
from app_backend.services.query_sanitizer import SanitizedQuery, sanitize_query
from app_backend.services.search_config_loader import (
    SearchAdapterConfig,
    load_search_config,
)
from app_backend.services.search_runtime_policy import (
    BlockedAdapterError,
    guard_search_runtime_policy,
)
from app_backend.services.tavily_adapter import TavilyAdapter


ConfigLoader = Callable[[], SearchAdapterConfig]
Sanitizer = Callable[[str], SanitizedQuery]
SearchAdapterLike = Callable[[SearchRequest], SearchResponse]
AdapterFactory = Callable[[SearchAdapterConfig, SearchRuntimePolicy], object]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryDailySearchBudget:
    """Process-local, per-UTC-day search call budget.

    The budget lives only in memory for the current process. It rolls over
    automatically at the UTC date boundary and is reset on restart. It never
    writes SQLite, files, cache, or logs. Reservation is atomic under a lock
    and happens before any transport call.
    """

    def __init__(self, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._lock = threading.Lock()
        self._now = now_provider or _utc_now
        self._date: date | None = None
        self._used = 0

    def _rollover_locked(self) -> None:
        today = self._now().date()
        if self._date != today:
            self._date = today
            self._used = 0

    def has_capacity(self, limit: int) -> bool:
        with self._lock:
            self._rollover_locked()
            return limit > 0 and self._used < limit

    def reserve(self, limit: int) -> bool:
        with self._lock:
            self._rollover_locked()
            if limit > 0 and self._used < limit:
                self._used += 1
                return True
            return False


def _fail_closed() -> SearchResponse:
    return SearchResponse(results=[], search_available=False, guard_passed=False)


class TavilySearchExecutionService:
    """Route-free, fail-closed search execution control plane.

    Computes a per-request runtime policy from real state, requires explicit
    user confirmation, enforces a process-local daily budget, and only wires
    the Tavily adapter after every gate has passed and the budget is reserved.

    Construction, import, and the default factory never read config, env, or
    files, never call the transport, never make network calls, and never
    consume budget. Config is read only inside ``execute()``.
    """

    def __init__(
        self,
        *,
        config_loader: ConfigLoader = load_search_config,
        budget: InMemoryDailySearchBudget | None = None,
        adapter_factory: AdapterFactory | None = None,
        sanitizer: Sanitizer = sanitize_query,
    ) -> None:
        self._config_loader = config_loader
        self._budget = budget if budget is not None else InMemoryDailySearchBudget()
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._sanitizer = sanitizer

    def execute(self, request: TavilySearchApiRequest) -> SearchResponse:
        # 1. Sanitize. A blocked query never reads config or touches transport,
        #    and never echoes the raw query or findings back.
        sanitized = self._sanitizer(request.query)
        if sanitized.blocked:
            return _fail_closed()

        # 2. Explicit user confirmation. Without it, no config read, no
        #    transport creation, no Tavily call.
        if not request.confirm_external_search:
            return _fail_closed()

        # 3. Read config (only now). Any loader failure fails closed.
        try:
            config = self._config_loader()
        except Exception:
            return _fail_closed()
        if not isinstance(config, SearchAdapterConfig):
            return _fail_closed()

        allowlist = [
            domain
            for domain in config.domain_allowlist
            if isinstance(domain, str) and domain.strip()
        ]
        budget_limit = config.daily_call_budget

        # 4-5. Build the runtime policy from real state (never hardcoded).
        policy = SearchRuntimePolicy(
            search_enabled=config.enabled,
            provider_network_enabled=config.enabled,
            user_controlled_switch_enabled=request.confirm_external_search,
            single_request_user_approved=request.confirm_external_search,
            query_sanitizer_passed=not sanitized.blocked,
            domain_allowlist_enforced=bool(allowlist),
            response_guard_required=True,
            budget_within_limit=self._budget.has_capacity(budget_limit),
            save_raw_query=False,
            save_raw_html=False,
            allow_holdings_in_query=False,
            allow_position_in_query=False,
            allow_account_in_query=False,
            allow_local_path_in_query=False,
        )

        # 6. Guard the policy. Disabled / empty allowlist / budget=0 /
        #    exhausted budget all fail closed here, before any reserve.
        if not guard_search_runtime_policy(policy).allowed:
            return _fail_closed()

        # 7. Atomically reserve the daily budget before constructing transport.
        if not self._budget.reserve(budget_limit):
            return _fail_closed()

        # 8-9. Only now build the adapter (with real transport) and search.
        try:
            adapter = self._adapter_factory(config, policy)
            response = adapter.search(
                SearchRequest(
                    query=request.query,
                    max_results=request.max_results,
                    domain_filter=list(request.domain_filter),
                )
            )
        except BlockedAdapterError:
            return _fail_closed()
        except Exception:
            return _fail_closed()

        if not isinstance(response, SearchResponse):
            return _fail_closed()
        return response


def _default_adapter_factory(
    config: SearchAdapterConfig,
    policy: SearchRuntimePolicy,
) -> TavilyAdapter:
    # Lazy import keeps the transport (and its HTTP client) out of module
    # import. The transport is only created after every gate and the reserve.
    from app_backend.services.tavily_real_transport import TavilyRealTransport

    transport = TavilyRealTransport(
        endpoint=config.tavily_endpoint,
        timeout_seconds=config.timeout_seconds,
    )
    return TavilyAdapter(
        config=config,
        transport=transport,
        runtime_policy=policy,
    )


def build_default_tavily_search_execution_service() -> TavilySearchExecutionService:
    return TavilySearchExecutionService(
        config_loader=load_search_config,
        budget=InMemoryDailySearchBudget(),
        adapter_factory=_default_adapter_factory,
    )


__all__ = [
    "InMemoryDailySearchBudget",
    "TavilySearchExecutionService",
    "build_default_tavily_search_execution_service",
]
