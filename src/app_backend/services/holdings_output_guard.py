"""Fail-closed guard for detailed holdings disclosure in MacroBrief output."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app_backend.schemas.holdings_snapshot import HoldingsSnapshot, normalize_holdings_snapshot
from app_backend.schemas.macro_brief import MacroBrief


DISCLOSURE_WARNING_CODE = "holdings_output_disclosure_blocked"
_NUMERIC_FIELDS = (
    "quantity",
    "average_cost",
    "total_cost",
    "latest_price",
    "market_value",
    "unrealized_pnl",
    "realized_pnl",
)


def find_holdings_output_disclosures(
    *,
    brief: MacroBrief,
    holdings_snapshot: HoldingsSnapshot | dict[str, Any] | None,
) -> list[str]:
    output_text = json.dumps(brief.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return find_holdings_text_disclosures(
        output_text=output_text,
        holdings_snapshot=holdings_snapshot,
    )


def find_holdings_text_disclosures(
    *,
    output_text: str,
    holdings_snapshot: HoldingsSnapshot | dict[str, Any] | None,
) -> list[str]:
    if holdings_snapshot is None:
        return []
    snapshot = (
        holdings_snapshot
        if isinstance(holdings_snapshot, HoldingsSnapshot)
        else normalize_holdings_snapshot(holdings_snapshot)
    )
    findings: list[str] = []

    if snapshot.account_name and snapshot.account_name in output_text:
        findings.append("account_name")

    for index, position in enumerate(snapshot.positions):
        for field_name in _NUMERIC_FIELDS:
            value = getattr(position, field_name)
            if value is None:
                continue
            if _numeric_value_appears(output_text, value):
                findings.append(f"positions[{index}].{field_name}")

    return findings


def _numeric_value_appears(text: str, value: float) -> bool:
    variants = _numeric_variants(value)
    return any(variant and variant in text for variant in variants)


def _numeric_variants(value: float) -> set[str]:
    try:
        decimal_value = Decimal(str(value)).normalize()
    except InvalidOperation:
        return {str(value)}
    plain = format(decimal_value, "f")
    variants = {plain, str(value)}
    if "." in plain:
        variants.add(plain.rstrip("0").rstrip("."))
    else:
        variants.add(f"{plain}.0")
    try:
        variants.add(f"{float(decimal_value):,.0f}")
        variants.add(f"{float(decimal_value):,.2f}")
    except (OverflowError, ValueError):
        pass
    return {variant for variant in variants if variant}


__all__ = [
    "DISCLOSURE_WARNING_CODE",
    "find_holdings_output_disclosures",
    "find_holdings_text_disclosures",
]
