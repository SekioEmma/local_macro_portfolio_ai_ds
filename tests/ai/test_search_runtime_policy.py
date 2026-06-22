from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_backend.schemas.search_external import SearchRuntimePolicy
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
    assert set(result.blocking_flags) == {
        *REQUIRED_TRUE_FIELDS,
        *REQUIRED_FALSE_FIELDS,
    }


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
        _allowed_policy(query_sanitized=False)
    )

    assert result.blocking_flags == ["query_sanitized"]


def test_blocking_flags_include_required_false_field_name():
    result = guard_search_runtime_policy(
        _allowed_policy(allow_pii_in_query=True)
    )

    assert result.blocking_flags == ["allow_pii_in_query"]


def test_blocking_flags_preserve_guard_order():
    result = guard_search_runtime_policy(
        _allowed_policy(
            search_enabled=False,
            transport_timeout_set=False,
            allow_account_data_in_query=True,
        )
    )

    assert result.blocking_flags == [
        "search_enabled",
        "transport_timeout_set",
        "allow_account_data_in_query",
    ]


def test_policy_is_frozen():
    policy = _allowed_policy()

    with pytest.raises(ValidationError):
        policy.search_enabled = False


def test_guard_is_deterministic():
    policy = _allowed_policy(domain_allowlist_configured=False)

    assert guard_search_runtime_policy(policy) == guard_search_runtime_policy(
        policy
    )


def test_blocked_error_message_contains_flag_names():
    with pytest.raises(BlockedAdapterError) as exc:
        assert_search_runtime_policy_allowed(
            _allowed_policy(
                daily_budget_available=False,
                allow_unlimited_calls=True,
            )
        )

    assert "daily_budget_available" in str(exc.value)
    assert "allow_unlimited_calls" in str(exc.value)
