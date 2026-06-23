from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app_backend.main import (
    app,
    get_tavily_search_execution_service,
)
from app_backend.schemas.search_external import (
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app_backend.services.search_config_loader import SearchAdapterConfig
from app_backend.services.search_execution_service import (
    InMemoryDailySearchBudget,
    TavilySearchExecutionService,
)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    return TestClient(app)


class SpyConfigLoader:
    def __init__(self, config: SearchAdapterConfig) -> None:
        self.calls = 0
        self.config = config

    def __call__(self) -> SearchAdapterConfig:
        self.calls += 1
        return self.config


class FakeAdapter:
    def __init__(
        self,
        response: SearchResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[SearchRequest] = []
        self.response = response
        self.error = error

    def search(self, request: SearchRequest) -> SearchResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FakeAdapterFactory:
    def __init__(self, adapter: FakeAdapter) -> None:
        self.calls = 0
        self.adapter = adapter

    def __call__(self, config, policy) -> FakeAdapter:
        self.calls += 1
        return self.adapter


def _config(
    *,
    enabled: bool = True,
    allowlist: tuple[str, ...] = ("reuters.com",),
    budget: int = 10,
) -> SearchAdapterConfig:
    return SearchAdapterConfig(
        enabled=enabled,
        daily_call_budget=budget,
        domain_allowlist=list(allowlist),
    )


def _ok_response() -> SearchResponse:
    return SearchResponse(
        results=[
            SearchResult(
                url="https://reuters.com/markets",
                title="Markets",
                snippet="Yields mixed.",
                domain="reuters.com",
            )
        ],
        search_available=True,
        guard_passed=True,
    )


def _install_service(
    *,
    loader: SpyConfigLoader,
    factory: FakeAdapterFactory,
    budget: InMemoryDailySearchBudget | None = None,
) -> TavilySearchExecutionService:
    service = TavilySearchExecutionService(
        config_loader=loader,
        budget=budget or InMemoryDailySearchBudget(),
        adapter_factory=factory,
    )
    app.dependency_overrides[get_tavily_search_execution_service] = (
        lambda: service
    )
    return service


def test_confirm_false_fails_closed_without_config_or_transport():
    loader = SpyConfigLoader(_config())
    factory = FakeAdapterFactory(FakeAdapter(_ok_response()))
    _install_service(loader=loader, factory=factory)

    response = _client().post(
        "/api/search/tavily",
        json={"query": "rate outlook", "confirm_external_search": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["search_available"] is False
    assert body["guard_passed"] is False
    assert loader.calls == 0
    assert factory.calls == 0


def test_sanitizer_blocked_fails_closed():
    loader = SpyConfigLoader(_config())
    factory = FakeAdapterFactory(FakeAdapter(_ok_response()))
    _install_service(loader=loader, factory=factory)

    response = _client().post(
        "/api/search/tavily",
        json={
            "query": "account number 123456789",
            "confirm_external_search": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["guard_passed"] is False
    assert loader.calls == 0
    assert factory.calls == 0


def test_disabled_config_fails_closed():
    loader = SpyConfigLoader(_config(enabled=False))
    factory = FakeAdapterFactory(FakeAdapter(_ok_response()))
    _install_service(loader=loader, factory=factory)

    response = _client().post(
        "/api/search/tavily",
        json={"query": "rate outlook", "confirm_external_search": True},
    )

    assert response.status_code == 200
    assert response.json()["search_available"] is False
    assert factory.calls == 0


def test_budget_exhausted_fails_closed():
    loader = SpyConfigLoader(_config(budget=1))
    factory = FakeAdapterFactory(FakeAdapter(_ok_response()))
    _install_service(loader=loader, factory=factory)
    client = _client()

    first = client.post(
        "/api/search/tavily",
        json={"query": "rate outlook", "confirm_external_search": True},
    )
    second = client.post(
        "/api/search/tavily",
        json={"query": "rate outlook", "confirm_external_search": True},
    )

    assert first.json()["search_available"] is True
    assert second.json()["guard_passed"] is False
    assert factory.calls == 1


def test_successful_fake_search_returns_results():
    loader = SpyConfigLoader(_config())
    factory = FakeAdapterFactory(FakeAdapter(_ok_response()))
    _install_service(loader=loader, factory=factory)

    response = _client().post(
        "/api/search/tavily",
        json={"query": "federal reserve outlook", "confirm_external_search": True},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["search_available"] is True
    assert body["guard_passed"] is True
    assert len(body["results"]) == 1


def test_transport_unavailable_returns_safe_passthrough():
    unavailable = SearchResponse(
        results=[], search_available=False, guard_passed=True
    )
    loader = SpyConfigLoader(_config())
    factory = FakeAdapterFactory(FakeAdapter(unavailable))
    _install_service(loader=loader, factory=factory)

    response = _client().post(
        "/api/search/tavily",
        json={"query": "rate outlook", "confirm_external_search": True},
    )

    body = response.json()
    assert body["search_available"] is False
    assert body["guard_passed"] is True


def test_response_body_has_no_query_secret_or_flags():
    loader = SpyConfigLoader(_config())
    factory = FakeAdapterFactory(FakeAdapter(_ok_response()))
    _install_service(loader=loader, factory=factory)

    secret = "uniquesecretphrase"
    response = _client().post(
        "/api/search/tavily",
        json={
            "query": f"{secret} balance $100000",
            "confirm_external_search": True,
        },
    )

    text = response.text
    assert secret not in text
    assert "blocking_flags" not in text
    assert "api_key" not in text


def test_get_method_not_allowed():
    response = _client().get("/api/search/tavily")
    assert response.status_code == 405


def test_no_forbidden_routes_present():
    paths = {route.path for route in app.routes}
    assert "/api/search/tavily" in paths
    assert "/api/chat" not in paths
    assert "/api/ai/tavily" not in paths
