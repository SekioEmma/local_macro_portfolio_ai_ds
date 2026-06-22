from __future__ import annotations

import importlib
import sys

import pytest

from app_backend.schemas.search_external import (
    SearchRequest,
    SearchRuntimePolicy,
)
from app_backend.services.search_config_loader import SearchAdapterConfig
from app_backend.services.search_runtime_policy import BlockedAdapterError
from app_backend.services.tavily_adapter import (
    FakeTavilyAdapter,
    TavilyAdapter,
)
from app_backend.services.tavily_transport_contract import (
    TavilyTransportError,
    TavilyTransportRequest,
    TavilyTransportResponse,
    TavilyTransportResult,
)


def _policy(**overrides: bool) -> SearchRuntimePolicy:
    values = {
        "search_enabled": True,
        "provider_network_enabled": True,
        "user_controlled_switch_enabled": True,
        "single_request_user_approved": True,
        "query_sanitizer_passed": True,
        "domain_allowlist_enforced": True,
        "response_guard_required": True,
        "budget_within_limit": True,
        "save_raw_query": False,
        "save_raw_html": False,
        "allow_holdings_in_query": False,
        "allow_position_in_query": False,
        "allow_account_in_query": False,
        "allow_local_path_in_query": False,
        **overrides,
    }
    return SearchRuntimePolicy(**values)


def _config(
    *,
    allowlist: list[str] | None = None,
    blocklist: list[str] | None = None,
) -> SearchAdapterConfig:
    return SearchAdapterConfig(
        daily_call_budget=10,
        domain_allowlist=(
            ["reuters.com", "federalreserve.gov"]
            if allowlist is None
            else allowlist
        ),
        domain_blocklist=[] if blocklist is None else blocklist,
    )


class SpyTransport:
    def __init__(
        self,
        response: TavilyTransportResponse | None = None,
        error_kind: str | None = None,
    ) -> None:
        self.calls: list[TavilyTransportRequest] = []
        self.response = response or TavilyTransportResponse()
        self.error_kind = error_kind

    def send(
        self,
        request: TavilyTransportRequest,
    ) -> TavilyTransportResponse:
        self.calls.append(request)
        if self.error_kind is not None:
            raise TavilyTransportError(self.error_kind, "hidden detail")
        return self.response


def _result(
    url: str = "https://www.reuters.com/markets/rates",
    *,
    title: str = "Rates update",
    snippet: str = "Policy-sensitive yields were mixed.",
) -> TavilyTransportResult:
    return TavilyTransportResult(
        url=url,
        title=title,
        snippet=snippet,
    )


def _adapter(
    transport,
    *,
    config: SearchAdapterConfig | None = None,
    policy: SearchRuntimePolicy | None = None,
):
    return TavilyAdapter(
        config=config or _config(),
        transport=transport,
        runtime_policy=policy or _policy(),
    )


def test_success_path_maps_guarded_results():
    transport = SpyTransport(
        TavilyTransportResponse(results=[_result()])
    )

    response = _adapter(transport).search(
        SearchRequest(query="Federal Reserve rate outlook")
    )

    assert response.search_available is True
    assert response.guard_passed is True
    assert len(response.results) == 1
    assert response.results[0].domain == "reuters.com"
    assert len(transport.calls) == 1


def test_empty_request_filter_uses_full_config_allowlist():
    transport = SpyTransport()

    _adapter(transport).search(SearchRequest(query="inflation outlook"))

    assert transport.calls[0].include_domains == [
        "reuters.com",
        "federalreserve.gov",
    ]


def test_request_filter_is_case_insensitive_and_normalizes_www():
    transport = SpyTransport()

    _adapter(transport).search(
        SearchRequest(
            query="inflation outlook",
            domain_filter=["WWW.Reuters.COM"],
        )
    )

    assert transport.calls[0].include_domains == ["reuters.com"]


def test_request_subdomain_is_allowed_by_parent_allowlist():
    transport = SpyTransport()

    _adapter(transport).search(
        SearchRequest(
            query="markets rates outlook",
            domain_filter=["markets.reuters.com"],
        )
    )

    assert transport.calls[0].include_domains == ["markets.reuters.com"]


def test_evil_suffix_domain_is_rejected_without_transport_call():
    transport = SpyTransport()

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter(transport).search(
            SearchRequest(
                query="rates outlook",
                domain_filter=["evilreuters.com"],
            )
        )

    assert exc.value.blocking_flags == ["domain_not_allowlisted"]
    assert transport.calls == []


def test_sanitizer_blocks_query_before_policy_or_transport():
    transport = SpyTransport()

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter(transport).search(
            SearchRequest(query=r"read C:\Users\Alice\holdings.csv")
        )

    assert "query_sanitizer_local_path" in exc.value.blocking_flags
    assert transport.calls == []


def test_runtime_policy_failure_prevents_transport():
    transport = SpyTransport()

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter(
            transport,
            policy=_policy(budget_within_limit=False),
        ).search(SearchRequest(query="rates outlook"))

    assert "budget_within_limit" in exc.value.blocking_flags
    assert transport.calls == []


def test_missing_runtime_policy_fails_closed():
    transport = SpyTransport()
    adapter = TavilyAdapter(
        config=_config(),
        transport=transport,
        runtime_policy=None,
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.search(SearchRequest(query="rates outlook"))

    assert exc.value.blocking_flags == ["missing_runtime_policy"]
    assert transport.calls == []


def test_empty_allowlist_fails_closed():
    transport = SpyTransport()

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter(
            transport,
            config=_config(allowlist=[]),
        ).search(SearchRequest(query="rates outlook"))

    assert exc.value.blocking_flags == ["empty_domain_allowlist"]
    assert transport.calls == []


def test_blocklist_has_priority_over_allowlist():
    transport = SpyTransport()

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter(
            transport,
            config=_config(
                allowlist=["reuters.com"],
                blocklist=["reuters.com"],
            ),
        ).search(SearchRequest(query="rates outlook"))

    assert exc.value.blocking_flags == ["domain_blocklisted"]
    assert transport.calls == []


@pytest.mark.parametrize("kind", ["timeout", "http_error"])
def test_transport_errors_degrade_without_leaking_detail(kind: str):
    transport = SpyTransport(error_kind=kind)

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert response.results == []
    assert response.search_available is False
    assert response.guard_passed is True
    assert "hidden detail" not in response.model_dump_json()


def test_missing_transport_fails_closed():
    adapter = TavilyAdapter(
        config=_config(),
        transport=None,
        runtime_policy=_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.search(SearchRequest(query="rates outlook"))

    assert exc.value.blocking_flags == ["missing_transport"]


def test_malformed_transport_response_fails_closed():
    class MalformedTransport:
        def send(self, request):
            return {"results": []}

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter(MalformedTransport()).search(
            SearchRequest(query="rates outlook")
        )

    assert exc.value.blocking_flags == ["transport_malformed_response"]


def test_mixed_transport_domains_keep_only_allowed_results():
    transport = SpyTransport(
        TavilyTransportResponse(
            results=[
                _result(),
                _result("https://evil.example/rates"),
            ]
        )
    )

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert [result.domain for result in response.results] == ["reuters.com"]


def test_response_domain_is_derived_from_url_not_transport_field():
    result = _result("https://markets.reuters.com/rates")
    transport = SpyTransport(TavilyTransportResponse(results=[result]))

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert response.results[0].domain == "markets.reuters.com"


def test_invalid_url_is_filtered_without_fabrication():
    transport = SpyTransport(
        TavilyTransportResponse(results=[_result("not-a-url")])
    )

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert response.results == []
    assert response.search_available is True


def test_response_privacy_markers_are_filtered():
    transport = SpyTransport(
        TavilyTransportResponse(
            results=[
                _result(snippet="Authorization Bearer tvly-hidden"),
                _result(
                    "https://federalreserve.gov/policy",
                    title="Policy statement",
                ),
            ]
        )
    )

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    serialized = response.model_dump_json().lower()
    assert len(response.results) == 1
    assert "tvly-hidden" not in serialized
    assert "authorization" not in serialized


def test_response_may_include_sanitizer_approved_query():
    query = "unique raw query phrase"
    transport = SpyTransport(
        TavilyTransportResponse(
            results=[_result(title=f"Result for {query}")]
        )
    )

    response = _adapter(transport).search(SearchRequest(query=query))

    assert len(response.results) == 1
    assert query in response.results[0].title


def test_treasury_general_account_is_not_filtered():
    transport = SpyTransport(
        TavilyTransportResponse(
            results=[
                _result(
                    snippet="Treasury General Account balance changed."
                )
            ]
        )
    )

    response = _adapter(transport).search(
        SearchRequest(query="Treasury liquidity outlook")
    )

    assert len(response.results) == 1


@pytest.mark.parametrize(
    "snippet",
    [
        "account number 123456789",
        "账户号：123456789",
        "holdings line item details",
        "position weight 15 percent",
        "transaction history attached",
    ],
)
def test_specific_sensitive_response_content_is_filtered(snippet: str):
    transport = SpyTransport(
        TavilyTransportResponse(results=[_result(snippet=snippet)])
    )

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert response.results == []


def test_output_url_strips_query_and_fragment():
    transport = SpyTransport(
        TavilyTransportResponse(
            results=[
                _result(
                    "https://www.reuters.com/markets/rates"
                    "?q=rates%20outlook&token=secret#fragment"
                )
            ]
        )
    )

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert response.results[0].url == "https://reuters.com/markets/rates"
    assert "token" not in response.model_dump_json()
    assert "fragment" not in response.model_dump_json()


def test_url_with_userinfo_is_filtered():
    transport = SpyTransport(
        TavilyTransportResponse(
            results=[
                _result("https://user:password@reuters.com/markets/rates")
            ]
        )
    )

    response = _adapter(transport).search(
        SearchRequest(query="rates outlook")
    )

    assert response.results == []


def test_max_results_is_tightened_to_config_limit():
    transport = SpyTransport()

    _adapter(transport).search(
        SearchRequest(query="rates outlook", max_results=99)
    )

    assert transport.calls[0].max_results == 5


def test_fake_adapter_uses_full_guarded_transport_chain():
    transport = SpyTransport(
        TavilyTransportResponse(results=[_result()])
    )
    adapter = FakeTavilyAdapter(
        config=_config(),
        transport=transport,
        runtime_policy=_policy(),
    )

    response = adapter.search(SearchRequest(query="rates outlook"))

    assert len(transport.calls) == 1
    assert response.guard_passed is True
    assert response.results[0].domain == "reuters.com"


def test_fake_adapter_cannot_bypass_sanitizer():
    transport = SpyTransport()
    adapter = FakeTavilyAdapter(
        config=_config(),
        transport=transport,
        runtime_policy=_policy(),
    )

    with pytest.raises(BlockedAdapterError):
        adapter.search(SearchRequest(query="SPY:50%"))

    assert transport.calls == []


def test_adapter_import_has_no_file_or_network_side_effects(monkeypatch):
    def blocked_open(*args, **kwargs):
        raise AssertionError("adapter import must not open files")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("adapter import must not open sockets")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr("socket.socket", blocked_socket)
    sys.modules.pop("app_backend.services.tavily_adapter", None)

    module = importlib.import_module("app_backend.services.tavily_adapter")

    assert module.__name__ == "app_backend.services.tavily_adapter"
