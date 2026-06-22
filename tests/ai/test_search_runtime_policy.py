from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_backend.schemas.search_external import (
    SearchGuardResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchRuntimePolicy,
)
from app_backend.services.search_runtime_policy import (
    BlockedAdapterError,
    REQUIRED_FALSE_FIELDS,
    REQUIRED_TRUE_FIELDS,
    assert_search_runtime_policy_allowed,
    guard_search_runtime_policy,
)


def _allowed_policy(**overrides: bool) -> SearchRuntimePolicy:
    values = {
        **{field_name: True for field_name in REQUIRED_TRUE_FIELDS},
        **{field_name: False for field_name in REQUIRED_FALSE_FIELDS},
        **overrides,
    }
    return SearchRuntimePolicy(**values)


@pytest.mark.parametrize("field_name", REQUIRED_TRUE_FIELDS)
def test_each_required_true_field_fails_closed(field_name: str):
    policy = _allowed_policy(**{field_name: False})

    result = guard_search_runtime_policy(policy)

    assert result.allowed is False
    assert field_name in result.blocking_flags


@pytest.mark.parametrize("field_name", REQUIRED_FALSE_FIELDS)
def test_each_required_false_field_fails_closed(field_name: str):
    policy = _allowed_policy(**{field_name: True})

    result = guard_search_runtime_policy(policy)

    assert result.allowed is False
    assert field_name in result.blocking_flags


def test_default_policy_is_fully_fail_closed():
    result = guard_search_runtime_policy(SearchRuntimePolicy())

    assert result.allowed is False
    assert result.blocking_flags == list(REQUIRED_TRUE_FIELDS)


def test_all_correct_fields_allow_search():
    result = guard_search_runtime_policy(_allowed_policy())

    assert result.allowed is True
    assert result.blocking_flags == []


def test_assert_raises_when_policy_is_blocked():
    with pytest.raises(BlockedAdapterError) as exc:
        assert_search_runtime_policy_allowed(SearchRuntimePolicy())

    assert exc.value.blocking_flags


def test_assert_does_not_raise_when_policy_is_allowed():
    assert_search_runtime_policy_allowed(_allowed_policy())


def test_blocking_flags_include_required_true_field_name():
    result = guard_search_runtime_policy(
        _allowed_policy(query_sanitizer_passed=False)
    )

    assert result.blocking_flags == ["query_sanitizer_passed"]


def test_blocking_flags_include_required_false_field_name():
    result = guard_search_runtime_policy(
        _allowed_policy(allow_account_in_query=True)
    )

    assert result.blocking_flags == ["allow_account_in_query"]


def test_blocking_flags_preserve_guard_order():
    result = guard_search_runtime_policy(
        _allowed_policy(
            search_enabled=False,
            budget_within_limit=False,
            allow_account_in_query=True,
        )
    )

    assert result.blocking_flags == [
        "search_enabled",
        "budget_within_limit",
        "allow_account_in_query",
    ]


def test_policy_is_frozen():
    policy = _allowed_policy()

    with pytest.raises(ValidationError):
        policy.search_enabled = False


def test_guard_is_deterministic():
    policy = _allowed_policy(domain_allowlist_enforced=False)

    assert guard_search_runtime_policy(policy) == guard_search_runtime_policy(
        policy
    )


def test_blocked_error_message_contains_flag_names():
    with pytest.raises(BlockedAdapterError) as exc:
        assert_search_runtime_policy_allowed(
            _allowed_policy(
                budget_within_limit=False,
                save_raw_query=True,
            )
        )

    assert "budget_within_limit" in str(exc.value)
    assert "save_raw_query" in str(exc.value)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (SearchRuntimePolicy, {}),
        (SearchRequest, {"query": "rates outlook"}),
        (
            SearchResult,
            {
                "url": "https://reuters.com/rates",
                "title": "Rates",
                "snippet": "Summary",
                "domain": "reuters.com",
            },
        ),
        (
            SearchResponse,
            {
                "results": [],
                "search_available": False,
                "guard_passed": False,
            },
        ),
        (
            SearchGuardResult,
            {"allowed": False, "blocking_flags": []},
        ),
    ],
)
def test_search_schemas_reject_unknown_fields(model, values):
    with pytest.raises(ValidationError):
        model(**values, unknown_field=True)
