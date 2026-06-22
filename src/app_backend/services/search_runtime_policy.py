from __future__ import annotations

from app_backend.schemas.search_external import (
    SearchGuardResult,
    SearchRuntimePolicy,
)


REQUIRED_TRUE_FIELDS = (
    "search_enabled",
    "provider_network_enabled",
    "user_controlled_switch_enabled",
    "single_request_user_approved",
    "query_sanitizer_passed",
    "domain_allowlist_enforced",
    "response_guard_required",
    "budget_within_limit",
)

REQUIRED_FALSE_FIELDS = (
    "save_raw_query",
    "save_raw_html",
    "allow_holdings_in_query",
    "allow_position_in_query",
    "allow_account_in_query",
    "allow_local_path_in_query",
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
