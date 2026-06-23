from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from app_backend.schemas.search_external import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchRuntimePolicy,
    TavilySearchApiRequest,
)
from app_backend.services.search_config_loader import SearchAdapterConfig
from app_backend.services.search_execution_service import (
    InMemoryDailySearchBudget,
    TavilySearchExecutionService,
    build_default_tavily_search_execution_service,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_SOURCE = (
    _REPO_ROOT / "src/app_backend/services/search_execution_service.py"
)


def _config(
    *,
    enabled: bool = True,
    allowlist: tuple[str, ...] = ("reuters.com",),
    blocklist: tuple[str, ...] = (),
    budget: int = 10,
    max_results: int = 5,
) -> SearchAdapterConfig:
    return SearchAdapterConfig(
        enabled=enabled,
        daily_call_budget=budget,
        max_results_per_call=max_results,
        domain_allowlist=list(allowlist),
        domain_blocklist=list(blocklist),
    )


def _ok_response() -> SearchResponse:
    return SearchResponse(
        results=[
            SearchResult(
                url="https://reuters.com/markets",
                title="Markets update",
                snippet="Yields were mixed.",
                domain="reuters.com",
            )
        ],
        search_available=True,
        guard_passed=True,
    )


def _request(
    *,
    query: str = "federal reserve rate outlook",
    confirm: bool = True,
    max_results: int = 5,
    domain_filter: list[str] | None = None,
) -> TavilySearchApiRequest:
    return TavilySearchApiRequest(
        query=query,
        confirm_external_search=confirm,
        max_results=max_results,
        domain_filter=domain_filter or [],
    )


class SpyConfigLoader:
    def __init__(
        self,
        config: SearchAdapterConfig | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.calls = 0
        self.config = config
        self.error = error

    def __call__(self) -> SearchAdapterConfig:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.config is not None
        return self.config


class SpyAdapter:
    def __init__(
        self,
        response: SearchResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[SearchRequest] = []
        self.response = response if response is not None else _ok_response()
        self.error = error

    def search(self, request: SearchRequest) -> SearchResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class SpyAdapterFactory:
    def __init__(self, adapter: SpyAdapter) -> None:
        self.calls: list[tuple[SearchAdapterConfig, SearchRuntimePolicy]] = []
        self.adapter = adapter

    def __call__(
        self,
        config: SearchAdapterConfig,
        policy: SearchRuntimePolicy,
    ) -> SpyAdapter:
        self.calls.append((config, policy))
        return self.adapter


def _service(
    *,
    config_loader: SpyConfigLoader,
    adapter_factory: SpyAdapterFactory | None = None,
    budget: InMemoryDailySearchBudget | None = None,
) -> tuple[TavilySearchExecutionService, SpyAdapterFactory]:
    factory = adapter_factory or SpyAdapterFactory(SpyAdapter())
    service = TavilySearchExecutionService(
        config_loader=config_loader,
        budget=budget or InMemoryDailySearchBudget(),
        adapter_factory=factory,
    )
    return service, factory


# --------------------------------------------------------------------------
# Import / construction / default factory must touch nothing.
# --------------------------------------------------------------------------
def test_import_has_no_file_or_network_side_effects(monkeypatch):
    def blocked_open(*args, **kwargs):
        raise AssertionError("import must not open files")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("import must not open sockets")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr("socket.socket", blocked_socket)
    sys.modules.pop("app_backend.services.search_execution_service", None)

    module = importlib.import_module(
        "app_backend.services.search_execution_service"
    )

    assert hasattr(module, "TavilySearchExecutionService")
    assert hasattr(module, "InMemoryDailySearchBudget")


def test_construction_reads_no_config_and_calls_nothing():
    loader = SpyConfigLoader(_config())
    factory = SpyAdapterFactory(SpyAdapter())

    TavilySearchExecutionService(
        config_loader=loader,
        budget=InMemoryDailySearchBudget(),
        adapter_factory=factory,
    )

    assert loader.calls == 0
    assert factory.calls == []


def test_build_default_factory_reads_no_config(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app_backend.services.search_execution_service.load_search_config",
        lambda *a, **k: calls.append("read") or _config(),
    )

    service = build_default_tavily_search_execution_service()

    assert isinstance(service, TavilySearchExecutionService)
    assert calls == []


# --------------------------------------------------------------------------
# Pre-config gates
# --------------------------------------------------------------------------
def test_confirm_false_fails_closed_without_reading_config():
    loader = SpyConfigLoader(_config())
    service, factory = _service(config_loader=loader)

    response = service.execute(_request(confirm=False))

    assert response.results == []
    assert response.search_available is False
    assert response.guard_passed is False
    assert loader.calls == 0
    assert factory.calls == []


def test_sanitizer_block_fails_closed_without_reading_config():
    loader = SpyConfigLoader(_config())
    service, factory = _service(config_loader=loader)

    response = service.execute(_request(query="my account number 123456789"))

    assert response.search_available is False
    assert response.guard_passed is False
    assert loader.calls == 0
    assert factory.calls == []


def test_sanitizer_block_does_not_echo_query():
    loader = SpyConfigLoader(_config())
    service, _ = _service(config_loader=loader)

    secret = "uniquesecretphrase"
    response = service.execute(
        _request(query=f"{secret} balance $100000")
    )

    assert secret not in response.model_dump_json()


# --------------------------------------------------------------------------
# Config / policy gates fail closed
# --------------------------------------------------------------------------
def test_disabled_config_fails_closed():
    loader = SpyConfigLoader(_config(enabled=False))
    service, factory = _service(config_loader=loader)

    response = service.execute(_request())

    assert response.search_available is False
    assert response.guard_passed is False
    assert loader.calls == 1
    assert factory.calls == []


def test_empty_allowlist_fails_closed():
    loader = SpyConfigLoader(_config(allowlist=()))
    service, factory = _service(config_loader=loader)

    response = service.execute(_request())

    assert response.guard_passed is False
    assert factory.calls == []


def test_zero_budget_fails_closed():
    loader = SpyConfigLoader(_config(budget=0))
    service, factory = _service(config_loader=loader)

    response = service.execute(_request())

    assert response.guard_passed is False
    assert factory.calls == []


def test_config_loader_exception_fails_closed():
    loader = SpyConfigLoader(error=RuntimeError("raw config secret"))
    service, factory = _service(config_loader=loader)

    response = service.execute(_request())

    assert response.guard_passed is False
    assert factory.calls == []
    assert "raw config secret" not in response.model_dump_json()


def test_allowlisted_domain_rejection_fails_closed():
    # Real TavilyAdapter raises domain_not_allowlisted for an out-of-list
    # filter; the execution service must translate that to a safe response.
    loader = SpyConfigLoader(_config(allowlist=("reuters.com",)))
    service = TavilySearchExecutionService(
        config_loader=loader,
        budget=InMemoryDailySearchBudget(),
        adapter_factory=_real_adapter_factory,
    )

    response = service.execute(
        _request(domain_filter=["evil.example"])
    )

    assert response.search_available is False
    assert response.guard_passed is False


# --------------------------------------------------------------------------
# Budget mechanics
# --------------------------------------------------------------------------
def test_budget_exhaustion_fails_closed_after_limit():
    loader = SpyConfigLoader(_config(budget=2))
    factory = SpyAdapterFactory(SpyAdapter())
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    first = service.execute(_request())
    second = service.execute(_request())
    third = service.execute(_request())

    assert first.search_available is True
    assert second.search_available is True
    assert third.guard_passed is False
    assert len(factory.calls) == 2  # exactly one reserve per success


def test_successful_request_reserves_exactly_once():
    budget = InMemoryDailySearchBudget()
    loader = SpyConfigLoader(_config(budget=1))
    factory = SpyAdapterFactory(SpyAdapter())
    service, _ = _service(
        config_loader=loader,
        adapter_factory=factory,
        budget=budget,
    )

    service.execute(_request())
    blocked = service.execute(_request())

    assert blocked.guard_passed is False
    assert len(factory.calls) == 1


def test_utc_date_rollover_resets_budget():
    class FakeClock:
        def __init__(self, value: datetime) -> None:
            self.value = value

        def __call__(self) -> datetime:
            return self.value

    clock = FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    budget = InMemoryDailySearchBudget(now_provider=clock)
    loader = SpyConfigLoader(_config(budget=1))
    factory = SpyAdapterFactory(SpyAdapter())
    service, _ = _service(
        config_loader=loader,
        adapter_factory=factory,
        budget=budget,
    )

    assert service.execute(_request()).search_available is True
    assert service.execute(_request()).guard_passed is False

    clock.value = datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc)

    assert service.execute(_request()).search_available is True
    assert len(factory.calls) == 2


def test_no_transport_before_reserve_when_budget_zero():
    loader = SpyConfigLoader(_config(budget=0))
    factory = SpyAdapterFactory(SpyAdapter())
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    service.execute(_request())

    assert factory.calls == []


# --------------------------------------------------------------------------
# Adapter outcomes
# --------------------------------------------------------------------------
def test_successful_fake_adapter_path_returns_results():
    loader = SpyConfigLoader(_config())
    factory = SpyAdapterFactory(SpyAdapter(_ok_response()))
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    response = service.execute(_request())

    assert response.search_available is True
    assert response.guard_passed is True
    assert len(response.results) == 1
    assert len(factory.calls) == 1


def test_transport_unavailable_returns_safe_passthrough():
    unavailable = SearchResponse(
        results=[], search_available=False, guard_passed=True
    )
    loader = SpyConfigLoader(_config())
    factory = SpyAdapterFactory(SpyAdapter(unavailable))
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    response = service.execute(_request())

    assert response.search_available is False
    assert response.guard_passed is True


def test_unknown_adapter_exception_fails_closed():
    loader = SpyConfigLoader(_config())
    factory = SpyAdapterFactory(
        SpyAdapter(error=RuntimeError("hidden adapter detail"))
    )
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    response = service.execute(_request())

    assert response.search_available is False
    assert response.guard_passed is False
    assert "hidden adapter detail" not in response.model_dump_json()


# --------------------------------------------------------------------------
# Policy derivation
# --------------------------------------------------------------------------
def test_policy_has_eight_true_six_false_derived_from_state():
    loader = SpyConfigLoader(_config())
    factory = SpyAdapterFactory(SpyAdapter())
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    service.execute(_request())

    _, policy = factory.calls[0]
    assert policy.search_enabled is True
    assert policy.provider_network_enabled is True
    assert policy.user_controlled_switch_enabled is True
    assert policy.single_request_user_approved is True
    assert policy.query_sanitizer_passed is True
    assert policy.domain_allowlist_enforced is True
    assert policy.response_guard_required is True
    assert policy.budget_within_limit is True
    assert policy.save_raw_query is False
    assert policy.save_raw_html is False
    assert policy.allow_holdings_in_query is False
    assert policy.allow_position_in_query is False
    assert policy.allow_account_in_query is False
    assert policy.allow_local_path_in_query is False


def test_policy_search_enabled_follows_disabled_config():
    # Disabled config must flip search_enabled false and block before adapter,
    # proving the gate is derived from config state, not hardcoded true.
    loader = SpyConfigLoader(_config(enabled=False))
    factory = SpyAdapterFactory(SpyAdapter())
    service, _ = _service(config_loader=loader, adapter_factory=factory)

    response = service.execute(_request())

    assert response.guard_passed is False
    assert factory.calls == []


# --------------------------------------------------------------------------
# Source-level boundary
# --------------------------------------------------------------------------
def test_search_execution_source_has_no_forbidden_imports():
    source = _SERVICE_SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "import httpx",
        "import requests",
        "import aiohttp",
        "os.environ",
        "os.getenv",
        "sqlite3",
        "FastAPI",
    ):
        assert forbidden not in source


def _real_adapter_factory(config, policy):
    from app_backend.services.tavily_adapter import TavilyAdapter

    class _NeverCalledTransport:
        def send(self, request):  # pragma: no cover - must not be reached
            raise AssertionError("transport must not be reached")

    return TavilyAdapter(
        config=config,
        transport=_NeverCalledTransport(),
        runtime_policy=policy,
    )
