from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "data_sources.yaml"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import market_data_service  # noqa: E402


OFFICIAL_SOURCE_TIERS = {
    "official_api",
    "official_fallback",
    "official_or_public_data_api",
}
ALLOWED_SOURCE_BADGES = {
    "official",
    "official_fallback",
    "derived",
    "proxy",
    "unofficial_fallback",
    "research_needed",
    "missing",
    "not_available",
    "local",
    "search-derived",
}
REQUIRED_D14_FIELDS = (
    "source",
    "source_badge",
    "source_series",
    "provider",
    "unit",
    "expected_frequency",
    "interpretation_hint",
    "ai_context_allowed_rule",
)
D14_EXPECTED_MAPPINGS = {
    "sofr": ("SOFR", "official"),
    "effr": ("EFFR", "official"),
    "iorb": ("IORB", "official"),
    "on_rrp": ("RRPONTSYD", "official"),
    "commercial_paper_rate": ("DCPF3M", "official_fallback"),
    "stl_fsi": ("STLFSI4", "official_fallback"),
    "nfci": ("NFCI", "official_fallback"),
    "anfci": ("ANFCI", "official_fallback"),
}
REFERENCE_ONLY_SERIES = {"BAA10Y", "BAA10YM"}
BLOCKED_FACT_LAYER_ITEMS = ("valuation_proxy", "fedwatch_probability")


@dataclass(frozen=True)
class Finding:
    category: str
    severity: str
    item: str
    message: str


def load_data_sources(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    return market_data_service.load_data_source_config(str(path))


def audit_data_sources(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_audit_ppi_final_demand(config))
    findings.extend(_audit_source_tier_consistency(config))
    findings.extend(_audit_liquidity_funding_registry(config))
    findings.extend(_audit_blocked_fact_layer_items(config))
    findings.extend(_audit_source_badges(config))
    findings.extend(_audit_missing_reason_fields(config))
    findings.extend(_audit_reference_only_aliases(config))
    return findings


def format_findings(findings: list[Finding]) -> str:
    errors = [item for item in findings if item.severity == "error"]
    lines = [
        "Data Foundation Gap Audit",
        f"status: {'FAIL' if errors else 'PASS'}",
        f"findings: {len(findings)}",
        f"errors: {len(errors)}",
        "",
    ]
    for category in (
        "inconsistent_source_tiers",
        "research_needed_items",
        "not_available_items",
        "official_mapping_candidates",
        "proxy_reference_only_items",
        "forbidden_alias_risks",
        "source_badge_policy",
        "metadata_completeness",
    ):
        items = [item for item in findings if item.category == category]
        lines.append(f"{category}:")
        if not items:
            lines.append("  - none")
            continue
        for item in items:
            lines.append(f"  - {item.severity}: {item.item}: {item.message}")
    return "\n".join(lines)


def findings_to_payload(findings: list[Finding]) -> dict[str, Any]:
    errors = [item for item in findings if item.severity == "error"]
    return {
        "status": "FAIL" if errors else "PASS",
        "finding_count": len(findings),
        "error_count": len(errors),
        "findings": [asdict(item) for item in findings],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit source-gated data foundation gaps without network or writes."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to configs/data_sources.yaml.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit compact JSON instead of text.",
    )
    args = parser.parse_args(argv)
    config = load_data_sources(args.config)
    findings = audit_data_sources(config)
    payload = findings_to_payload(findings)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_findings(findings))
    return 1 if payload["status"] == "FAIL" else 0


def _audit_ppi_final_demand(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    fred = _section(config, "fred_series")
    data_quality = _section(config, "data_quality")
    package = _section(_section(config, "deepseek_market_data_package"), "inflation_indicators")
    ppi_final = _section(fred, "ppi_final_demand")
    ppi_all = _section(fred, "ppi_all_commodities")
    package_final = _section(package, "ppi_final_demand")
    dq_final = _section(data_quality, "ppi_final_demand")

    if ppi_final.get("series_id") != "PPIFIS":
        findings.append(
            Finding(
                "inconsistent_source_tiers",
                "error",
                "fred_series.ppi_final_demand",
                "PPI final demand must map to PPIFIS.",
            )
        )
    if package_final.get("series_id") != "PPIFIS":
        findings.append(
            Finding(
                "inconsistent_source_tiers",
                "error",
                "deepseek_market_data_package.inflation_indicators.ppi_final_demand",
                "PPI final demand package mapping must be PPIFIS.",
            )
        )
    if ppi_all.get("series_id") == "PPIFIS":
        findings.append(
            Finding(
                "inconsistent_source_tiers",
                "error",
                "fred_series.ppi_all_commodities",
                "PPIACO/all-commodities PPI must stay separate from PPIFIS.",
            )
        )
    if dq_final.get("source_tier") == "research_needed":
        findings.append(
            Finding(
                "inconsistent_source_tiers",
                "error",
                "data_quality.ppi_final_demand",
                "PPIFIS is configured as an official/public source; data_quality must not remain research_needed.",
            )
        )
    if dq_final.get("source_tier") in OFFICIAL_SOURCE_TIERS:
        findings.append(
            Finding(
                "official_mapping_candidates",
                "info",
                "ppi_final_demand",
                "Configured as FRED PPIFIS official/public index; YoY remains historical-comparison gated.",
            )
        )
    unit = str(package_final.get("unit") or "").lower()
    hint = str(package_final.get("interpretation_hint") or "").lower()
    if unit != "index" or "distinct from ppiaco" not in hint:
        findings.append(
            Finding(
                "metadata_completeness",
                "error",
                "deepseek_market_data_package.inflation_indicators.ppi_final_demand",
                "PPI final demand must be documented as an index distinct from PPIACO.",
            )
        )
    return findings


def _audit_source_tier_consistency(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    fred = _section(config, "fred_series")
    data_quality = _section(config, "data_quality")
    official_elsewhere = _official_source_tier_by_key(config)
    for key, fred_item in fred.items():
        if not isinstance(fred_item, dict) or not fred_item.get("series_id"):
            continue
        dq_item = data_quality.get(key)
        if not isinstance(dq_item, dict):
            continue
        if dq_item.get("source_tier") == "research_needed" and key in official_elsewhere:
            if not dq_item.get("definition_note") and not dq_item.get("research_needed_reason"):
                findings.append(
                    Finding(
                        "inconsistent_source_tiers",
                        "error",
                        f"data_quality.{key}",
                        "FRED series and official/public mapping exist elsewhere but data_quality remains research_needed without reason.",
                    )
                )
    return findings


def _audit_liquidity_funding_registry(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    section = _section(config, "liquidity_funding_stress")
    for key, (series, badge) in D14_EXPECTED_MAPPINGS.items():
        item = _section(section, key)
        missing_fields = [field for field in REQUIRED_D14_FIELDS if item.get(field) in (None, "")]
        if missing_fields:
            findings.append(
                Finding(
                    "metadata_completeness",
                    "error",
                    f"liquidity_funding_stress.{key}",
                    f"Missing required fields: {', '.join(missing_fields)}.",
                )
            )
            continue
        if item.get("source_series") != series or item.get("source_badge") != badge:
            findings.append(
                Finding(
                    "inconsistent_source_tiers",
                    "error",
                    f"liquidity_funding_stress.{key}",
                    f"Expected {series}/{badge}; got {item.get('source_series')}/{item.get('source_badge')}.",
                )
            )
        else:
            findings.append(
                Finding(
                    "official_mapping_candidates",
                    "info",
                    key,
                    f"D14 mapped to {series} with source_badge={badge}.",
                )
            )

    ofr = _section(section, "ofr_fsi")
    if (
        ofr.get("status") != "research_needed"
        or ofr.get("source_badge") != "research_needed"
        or ofr.get("ai_context_allowed_rule") != "never_until_source_mapping_verified"
        or ofr.get("missing_reason") != "source_mapping_required"
    ):
        findings.append(
            Finding(
                "inconsistent_source_tiers",
                "error",
                "liquidity_funding_stress.ofr_fsi",
                "OFR FSI must remain research_needed and AI-ineligible until source mapping is verified.",
            )
        )
    else:
        findings.append(
            Finding(
                "research_needed_items",
                "info",
                "ofr_fsi",
                "Kept research_needed with source_mapping_required.",
            )
        )
    return findings


def _audit_blocked_fact_layer_items(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    financial = _section(config, "financial_conditions")
    unavailable = _section(_section(config, "deepseek_market_data_package"), "unavailable_or_research_needed")
    for key in BLOCKED_FACT_LAYER_ITEMS:
        financial_item = _section(financial, key)
        unavailable_item = _section(unavailable, key)
        if financial_item.get("provider") != "not_available" or financial_item.get("source_tier") != "not_available":
            findings.append(
                Finding(
                    "inconsistent_source_tiers",
                    "error",
                    f"financial_conditions.{key}",
                    "Must remain provider=not_available/source_tier=not_available.",
                )
            )
        if unavailable_item.get("status") != "not_available":
            findings.append(
                Finding(
                    "inconsistent_source_tiers",
                    "error",
                    f"deepseek_market_data_package.unavailable_or_research_needed.{key}",
                    "Must remain status=not_available.",
                )
            )
        findings.append(
            Finding(
                "not_available_items",
                "info",
                key,
                "Kept out of official factual layer.",
            )
        )
    return findings


def _audit_source_badges(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for path, value in _walk_key(config, "source_badge"):
        if value not in ALLOWED_SOURCE_BADGES:
            findings.append(
                Finding(
                    "source_badge_policy",
                    "error",
                    path,
                    f"source_badge={value!r} is outside the allowed set.",
                )
            )
    return findings


def _audit_missing_reason_fields(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for path, item in _walk_mappings(config):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        provider = item.get("provider")
        source_tier = item.get("source_tier")
        source_badge = item.get("source_badge")
        blocked = (
            status in {"missing", "research_needed", "not_available"}
            or provider in {"research_needed", "not_available"}
            or source_tier in {"research_needed", "not_available"}
            or source_badge in {"research_needed", "missing", "not_available"}
        )
        if not blocked:
            continue
        if item.get("missing_reason") or item.get("unavailable_reason") or item.get("definition_note"):
            continue
        findings.append(
            Finding(
                "metadata_completeness",
                "error",
                path,
                "missing/research_needed/not_available item lacks missing_reason or unavailable_reason.",
            )
        )
    return findings


def _audit_reference_only_aliases(config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    financial = _section(config, "financial_conditions")
    for key in ("high_yield_spread", "investment_grade_spread"):
        item = _section(financial, key)
        if str(item.get("series_id")) in REFERENCE_ONLY_SERIES:
            findings.append(
                Finding(
                    "forbidden_alias_risks",
                    "error",
                    f"financial_conditions.{key}",
                    "BAA10Y/BAA10YM must not alias to HY/IG OAS metric keys.",
                )
            )

    for path, value in _walk_values(config):
        if str(value) in REFERENCE_ONLY_SERIES:
            lowered_path = path.lower()
            if "reference" not in lowered_path and "proxy" not in lowered_path:
                findings.append(
                    Finding(
                        "proxy_reference_only_items",
                        "warning",
                        path,
                        f"{value} appears in config and must remain reference/proxy only.",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "proxy_reference_only_items",
                        "info",
                        path,
                        f"{value} is marked on a reference/proxy path.",
                    )
                )
    return findings


def _official_source_tier_by_key(config: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for path, item in _walk_mappings(config):
        if not isinstance(item, dict):
            continue
        if item.get("source_tier") in OFFICIAL_SOURCE_TIERS:
            result.add(path.rsplit(".", 1)[-1])
    return result


def _section(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key) if isinstance(mapping, dict) else None
    return value if isinstance(value, dict) else {}


def _walk_key(value: Any, key: str, prefix: str = "") -> list[tuple[str, Any]]:
    hits: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            path = f"{prefix}.{item_key}" if prefix else str(item_key)
            if item_key == key:
                hits.append((path, item_value))
            hits.extend(_walk_key(item_value, key, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            hits.extend(_walk_key(item, key, path))
    return hits


def _walk_mappings(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    hits: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        if prefix:
            hits.append((prefix, value))
        for item_key, item_value in value.items():
            path = f"{prefix}.{item_key}" if prefix else str(item_key)
            hits.extend(_walk_mappings(item_value, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_walk_mappings(item, f"{prefix}[{index}]"))
    return hits


def _walk_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    hits: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            path = f"{prefix}.{item_key}" if prefix else str(item_key)
            hits.extend(_walk_values(item_value, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_walk_values(item, f"{prefix}[{index}]"))
    else:
        hits.append((prefix, value))
    return hits


if __name__ == "__main__":
    raise SystemExit(main())
