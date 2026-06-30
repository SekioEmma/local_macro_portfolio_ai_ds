from __future__ import annotations

import json

import pytest

from app_backend.schemas.macro_brief import (
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_MODULE_KEYS,
    MacroBrief,
)
from app_backend.services.macro_brief_parser import (
    MacroBriefValidationError,
    parse_macro_brief,
)


def _brief_payload() -> dict:
    return {
        "core_conclusion": "Macro environment remains balanced.",
        "market_state": [
            {"symbol": symbol, "price": 400.0, "change_pct": 0.1, "as_of": "2026-06-28"}
            for symbol in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": [
            {
                "id": "f1",
                "statement": "DGS10 remained elevated.",
                "value": 4.3,
                "unit": "%",
                "source_id": "s1",
                "as_of": "2026-06-27",
            },
            {
                "id": "f2",
                "statement": "HY OAS stayed inside a watch range.",
                "value": 3.1,
                "unit": "%",
                "source_id": "s2",
                "as_of": "2026-06-27",
            },
        ],
        "judgments": [
            {
                "claim": "Rate pressure is still the main transmission channel.",
                "evidence_supports": ["f1"],
            }
        ],
        "module_table": [
            {"module_key": key, "module_name_zh": key, "status": "watch", "note": None}
            for key in REQUIRED_MODULE_KEYS
        ],
        "risk_assessment": {
            "current_label": "watch",
            "summary": "Risks are balanced but data-sensitive.",
            "upgrade_triggers": ["HY OAS widens materially"],
            "downgrade_triggers": ["Inflation and yields cool together"],
        },
        "forward_indicators": [
            {"name": f"indicator_{idx}", "release_date": "2026-07-11", "relevance": "next data point"}
            for idx in range(5)
        ],
        "scenarios": {
            "base": {
                "trigger_conditions": ["growth slows gradually"],
                "transmission_path": "yields stabilize and equities consolidate",
                "note": None,
            },
            "bullish": {
                "trigger_conditions": ["inflation cools faster"],
                "transmission_path": "real yields ease and duration recovers",
                "note": None,
            },
            "bearish": {
                "trigger_conditions": ["inflation reaccelerates"],
                "transmission_path": "rate pressure tightens financial conditions",
                "note": None,
            },
            "systemic": {
                "trigger_conditions": ["credit spreads gap wider"],
                "transmission_path": "funding stress spills into risk assets",
                "note": None,
            },
        },
        "source_list": [
            {"id": "s1", "url": "https://fred.stlouisfed.org/series/DGS10", "accessed_at": "2026-06-29"},
            {"id": "s2", "rag_doc_id": "credit_snapshot", "accessed_at": "2026-06-29"},
        ],
        "boundary_notice": " ".join(REQUIRED_BOUNDARY_KEYWORDS),
    }


def test_parse_macro_brief_accepts_mapping_payload():
    brief = parse_macro_brief(_brief_payload())

    assert isinstance(brief, MacroBrief)
    assert brief.market_state[0].symbol == "SPY"


def test_parse_macro_brief_normalizes_unavailable_market_state_and_claim_type():
    payload = _brief_payload()
    payload["market_state"][0]["price"] = "N/A"
    payload["market_state"][0]["change_pct"] = "unavailable"
    payload["market_state"][0]["as_of"] = "N/A"
    payload["market_state"][1]["change_pct"] = "+0.25%"
    payload["judgments"][0]["claim_type"] = "model_commentary"
    payload["source_list"].append(
        {"id": "empty-source", "accessed_at": "2026-06-29"}
    )
    payload["source_list"].append(
        {"id": "local-tool-source", "title": "Macro Dashboard", "accessed_at": "2026-06-29"}
    )

    brief = parse_macro_brief(payload)

    assert brief.market_state[0].price is None
    assert brief.market_state[0].change_pct is None
    assert brief.market_state[0].as_of is None
    assert brief.market_state[1].change_pct == 0.25
    assert brief.judgments[0].claim_type == "interpretive"
    assert all(source.id != "empty-source" for source in brief.source_list)
    assert any(source.id == "local-tool-source" for source in brief.source_list)


def test_parse_macro_brief_accepts_json_string_payload():
    brief = parse_macro_brief(json.dumps(_brief_payload()))

    assert brief.risk_assessment.current_label == "watch"


def test_parse_macro_brief_accepts_utf8_bytes_payload():
    brief = parse_macro_brief(json.dumps(_brief_payload()).encode("utf-8"))

    assert len(brief.forward_indicators) == 5


@pytest.mark.parametrize(
    "payload, expected",
    [
        ("", "json.empty_payload"),
        ("{not-json", "json.invalid:1:2"),
        ("[]", "json.expected_object"),
        (object(), "json.unsupported_payload_type:object"),
    ],
)
def test_parse_macro_brief_reports_json_level_errors(payload, expected):
    with pytest.raises(MacroBriefValidationError) as exc:
        parse_macro_brief(payload)

    assert expected in exc.value.errors
    assert exc.value.missing == ()
    assert exc.value.findings == ()


def test_parse_macro_brief_reports_missing_required_fields():
    payload = _brief_payload()
    del payload["source_list"]

    with pytest.raises(MacroBriefValidationError) as exc:
        parse_macro_brief(payload)

    assert exc.value.missing == ("source_list",)
    assert exc.value.errors == ()
    assert exc.value.findings == ()
    assert exc.value.to_dict()["missing"] == ["source_list"]


def test_parse_macro_brief_reports_field_validation_errors_without_input_values():
    payload = _brief_payload()
    payload["market_state"][0]["symbol"] = "BTC"

    with pytest.raises(MacroBriefValidationError) as exc:
        parse_macro_brief(payload)

    assert any(error.startswith("market_state[0].symbol:literal_error:") for error in exc.value.errors)
    assert "BTC" not in str(exc.value)


def test_parse_macro_brief_collects_cross_section_findings():
    payload = _brief_payload()
    payload["module_table"] = payload["module_table"][:5]
    payload["forward_indicators"] = payload["forward_indicators"][:3]
    payload["boundary_notice"] = "missing boundary language"

    with pytest.raises(MacroBriefValidationError) as exc:
        parse_macro_brief(payload)

    assert any("module_table.missing_module_keys" in finding for finding in exc.value.findings)
    assert any("forward_indicators.expected_5_got_3" in finding for finding in exc.value.findings)
    assert any("boundary_notice.missing_keywords" in finding for finding in exc.value.findings)
    assert exc.value.missing == ()
    assert exc.value.errors == ()


def test_macro_brief_validation_error_message_summarizes_counts():
    error = MacroBriefValidationError(
        missing=["core_conclusion"],
        errors=["json.invalid:1:2"],
        findings=["module_table.expected_6_rows_got_5"],
    )

    assert str(error) == "MacroBrief validation failed (missing=1, errors=1, findings=1)"
    assert error.all_issues == (
        "core_conclusion",
        "json.invalid:1:2",
        "module_table.expected_6_rows_got_5",
    )
