from __future__ import annotations

from app_backend.schemas.search_external import (
    SearchGuardResult,
    SearchRuntimePolicy,
)


REQUIRED_TRUE_FIELDS = (
    "policy_acknowledged",
    "search_enabled",
    "query_sanitized",
    "domain_allowlist_configured",
    "daily_budget_available",
    "response_guard_enabled",
    "result_classifier_enabled",
    "transport_timeout_set",
)

REQUIRED_FALSE_FIELDS = (
    "allow_raw_portfolio_in_query",
    "allow_account_data_in_query",
    "allow_pii_in_query",
    "allow_unlimited_calls",
    "allow_external_domain_bypass",
    "allow_query_without_sanitize",
)


class BlockedAdapterError(RuntimeError):
    def __init__(self, blocking_flags: list[str]) -> None:
        self.blocking_flags = list(blocking_flags)
        super().__init__(
            "Search runtime policy blocked: " + ", ".join(self.blocking_flags)
        )


def guard_search_runtime_policy(
    policy: SearchRuntimePolicy,
) -> SearchGuardResult:
    blocking_flags = [
        field_name
        for field_name in REQUIRED_TRUE_FIELDS
        if not getattr(policy, field_name)
    ]
    blocking_flags.extend(
        field_name
        for field_name in REQUIRED_FALSE_FIELDS
        if getattr(policy, field_name)
    )
    return SearchGuardResult(
        allowed=not blocking_flags,
        blocking_flags=blocking_flags,
    )


def assert_search_runtime_policy_allowed(
    policy: SearchRuntimePolicy,
) -> None:
    result = guard_search_runtime_policy(policy)
    if not result.allowed:
        raise BlockedAdapterError(result.blocking_flags)


__all__ = [
    "BlockedAdapterError",
    "REQUIRED_FALSE_FIELDS",
    "REQUIRED_TRUE_FIELDS",
    "assert_search_runtime_policy_allowed",
    "guard_search_runtime_policy",
]
