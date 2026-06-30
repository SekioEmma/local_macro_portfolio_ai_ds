from __future__ import annotations

import json as _json

import pytest
from pydantic import ValidationError

from app_backend.schemas.macro_brief import (
    FORWARD_INDICATOR_COUNT,
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_ETF_SYMBOLS,
    REQUIRED_MODULE_KEYS,
    REQUIRED_SCENARIO_KEYS,
    ConfirmedFact,
    ETFStateCard,
    ForwardIndicator,
    Judgment,
    MacroBrief,
    ModuleRow,
    RiskAssessment,
    ScenarioBlock,
    SourceItem,
    decode_findings,
)


def _etf_card(symbol: str = "SPY") -> ETFStateCard:
    return ETFStateCard(symbol=symbol, price=400.0, change_pct=0.5, as_of="2026-06-28")


def _fact(idx: str = "f1") -> ConfirmedFact:
    return ConfirmedFact(
        id=idx, statement="dgs10 was 4.30", value=4.30, unit="%",
        source_id=f"s_{idx}", evidence_ids=[f"ev_{idx}"], as_of="2026-06-27",
    )


def _judgment(supports: list[str] | None = None) -> Judgment:
    return Judgment(
        claim="rates remain elevated",
        evidence_supports=supports or ["f1"],
        evidence_ids=["ev_f1"],
        temporal_scope="current_run",
    )


def _module_row(module_key: str = "rate_pressure") -> ModuleRow:
    return ModuleRow(
        module_key=module_key,
        module_name_zh="利率压力",
        status="pressure",
        note=None,
    )


def _risk() -> RiskAssessment:
    return RiskAssessment(
        current_label="watch",
        summary="balanced risk",
        upgrade_triggers=["HY OAS > 4.5%"],
        downgrade_triggers=["HY OAS < 2.5%"],
    )


def _indicator(name: str = "CPI") -> ForwardIndicator:
    return ForwardIndicator(name=name, release_date="2026-07-11", relevance="inflation print")


def _scenario() -> ScenarioBlock:
    return ScenarioBlock(
        trigger_conditions=["inflation cooling"],
        transmission_path="rate-cut → equity multiple expansion",
        note=None,
    )


def _source(idx: str = "s_f1") -> SourceItem:
    return SourceItem(id=idx, url="https://federalreserve.gov/x", accessed_at="2026-06-29")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_required_module_keys_has_six():
    assert len(REQUIRED_MODULE_KEYS) == 6
    assert len(set(REQUIRED_MODULE_KEYS)) == 6  # no duplicates


def test_required_scenario_keys_has_four():
    assert REQUIRED_SCENARIO_KEYS == ("base", "bullish", "bearish", "systemic")


def test_required_etf_symbols_has_four():
    assert REQUIRED_ETF_SYMBOLS == ("SPY", "QQQ", "SHY", "GLD")


def test_required_boundary_keywords_has_five():
    assert len(REQUIRED_BOUNDARY_KEYWORDS) == 5
    for kw in ("非个股操作", "非概率胜率", "非收益预测", "非动态择时", "非黑盒最优化"):
        assert kw in REQUIRED_BOUNDARY_KEYWORDS


def test_forward_indicator_count_is_five():
    assert FORWARD_INDICATOR_COUNT == 5


# ---------------------------------------------------------------------------
# Frozen + extra forbidden across every section model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make",
    [
        _etf_card,
        _fact,
        _judgment,
        _module_row,
        _risk,
        _indicator,
        _scenario,
        _source,
    ],
)
def test_section_models_are_frozen(make):
    instance = make()
    first_field = next(iter(type(instance).model_fields))
    with pytest.raises(ValidationError):
        # Pydantic v2 frozen models raise on attribute set
        instance.__setattr__(first_field, "tampered")


def test_etf_state_card_rejects_extra_field():
    with pytest.raises(ValidationError):
        ETFStateCard(
            symbol="SPY", price=400.0, change_pct=0.5, as_of="2026-06-28", api_key="x"
        )


def test_confirmed_fact_rejects_extra_field():
    with pytest.raises(ValidationError):
        ConfirmedFact(id="f1", statement="x", source_id="s1", extra="x")


def test_judgment_rejects_extra_field():
    with pytest.raises(ValidationError):
        Judgment(claim="x", evidence_supports=["f1"], extra="x")


def test_module_row_rejects_extra_field():
    with pytest.raises(ValidationError):
        ModuleRow(module_key="rate_pressure", module_name_zh="x", status="watch", extra="x")


def test_macro_brief_rejects_extra_field():
    with pytest.raises(ValidationError):
        MacroBrief(
            core_conclusion="x",
            market_state=[_etf_card()],
            confirmed_facts=[_fact()],
            judgments=[_judgment()],
            module_table=[_module_row()],
            risk_assessment=_risk(),
            forward_indicators=[_indicator()],
            scenarios={"base": _scenario()},
            source_list=[_source()],
            boundary_notice="x",
            extra_field="should_fail",
        )


# ---------------------------------------------------------------------------
# Literal enforcement
# ---------------------------------------------------------------------------


def test_etf_symbol_rejects_unknown_ticker():
    with pytest.raises(ValidationError):
        ETFStateCard(symbol="BTC", price=1.0, change_pct=0.0, as_of="2026-06-28")


def test_module_key_rejects_unknown_key():
    with pytest.raises(ValidationError):
        ModuleRow(module_key="random_module", module_name_zh="x", status="watch")


def test_module_status_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ModuleRow(module_key="rate_pressure", module_name_zh="x", status="kinda_ok")


def test_scenario_key_rejects_unknown_key():
    with pytest.raises(ValidationError):
        # dict[Literal["base","bullish","bearish","systemic"], ScenarioBlock]
        MacroBrief(
            core_conclusion="x",
            market_state=[_etf_card()],
            confirmed_facts=[_fact()],
            judgments=[_judgment()],
            module_table=[_module_row()],
            risk_assessment=_risk(),
            forward_indicators=[_indicator()],
            scenarios={"crazy_scenario": _scenario()},
            source_list=[_source()],
            boundary_notice="x",
        )


def test_claim_type_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Judgment(claim="x", evidence_supports=["f1"], claim_type="speculation")


# ---------------------------------------------------------------------------
# Field requirements
# ---------------------------------------------------------------------------


def test_judgment_evidence_supports_must_be_non_empty():
    with pytest.raises(ValidationError):
        Judgment(claim="x", evidence_supports=[])


def test_risk_assessment_triggers_must_be_non_empty():
    with pytest.raises(ValidationError):
        RiskAssessment(
            current_label="watch",
            summary="x",
            upgrade_triggers=[],
            downgrade_triggers=["x"],
        )
    with pytest.raises(ValidationError):
        RiskAssessment(
            current_label="watch",
            summary="x",
            upgrade_triggers=["x"],
            downgrade_triggers=[],
        )


def test_scenario_block_trigger_conditions_non_empty():
    with pytest.raises(ValidationError):
        ScenarioBlock(trigger_conditions=[], transmission_path="x")


# ---------------------------------------------------------------------------
# MacroBrief end-to-end happy path (no cross-section validators yet)
# ---------------------------------------------------------------------------


def _full_brief() -> dict:
    return {
        "core_conclusion": "Macro environment remains balanced.",
        "market_state": [
            {"symbol": s, "price": 400.0, "change_pct": 0.1, "as_of": "2026-06-28"}
            for s in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": [_fact("f1").model_dump(), _fact("f2").model_dump()],
        "judgments": [
            {
                "claim": "x",
                "evidence_supports": ["f1"],
                "evidence_ids": ["ev_f1"],
                "temporal_scope": "current_run",
            }
        ],
        "module_table": [
            {"module_key": k, "module_name_zh": k, "status": "watch", "note": None}
            for k in REQUIRED_MODULE_KEYS
        ],
        "risk_assessment": _risk().model_dump(),
        "forward_indicators": [_indicator(f"i{i}").model_dump() for i in range(5)],
        "scenarios": {
            "base": _scenario().model_dump(),
            "bullish": _scenario().model_dump(),
            "bearish": _scenario().model_dump(),
            "systemic": _scenario().model_dump(),
        },
        "source_list": [
            _source("s_f1").model_dump(),
            _source("s_f2").model_dump(),
        ],
        "boundary_notice": (
            "本回答非个股操作、非概率胜率、非收益预测、非动态择时、非黑盒最优化。"
        ),
    }


def test_macro_brief_happy_path_validates():
    brief = MacroBrief.model_validate(_full_brief())
    assert brief.core_conclusion.startswith("Macro")
    assert len(brief.market_state) == 4
    assert len(brief.scenarios) == 4
    assert len(brief.forward_indicators) == 5


def test_macro_brief_serializes_back_to_dict():
    brief = MacroBrief.model_validate(_full_brief())
    payload = brief.model_dump(mode="json")
    # round-trip is stable
    MacroBrief.model_validate(payload)


# ---------------------------------------------------------------------------
# F2-2 cross-section validators
# ---------------------------------------------------------------------------


def _build_brief(**overrides) -> dict:
    brief = _full_brief()
    brief.update(overrides)
    return brief


def _findings_from(exc: ValidationError) -> list[str]:
    """Lift F2-2 cross-section findings out of a ValidationError."""
    for err in exc.errors():
        decoded = decode_findings(err.get("msg", ""))
        if decoded is not None:
            return decoded
    return []


def test_module_table_missing_keys_reported():
    rows = [
        {"module_key": k, "module_name_zh": k, "status": "watch", "note": None}
        for k in REQUIRED_MODULE_KEYS[:5]
    ]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(module_table=rows))

    findings = _findings_from(exc.value)
    assert any("module_table.missing_module_keys" in f for f in findings)


def test_module_table_extra_row_with_duplicate_key_reported():
    rows = [
        {"module_key": k, "module_name_zh": k, "status": "watch", "note": None}
        for k in REQUIRED_MODULE_KEYS
    ]
    rows.append({"module_key": "rate_pressure", "module_name_zh": "x", "status": "watch", "note": None})
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(module_table=rows))
    findings = _findings_from(exc.value)
    assert any("module_table.duplicate_module_key:rate_pressure" in f for f in findings)


def test_module_table_wrong_count_reported():
    rows = [
        {"module_key": k, "module_name_zh": k, "status": "watch", "note": None}
        for k in REQUIRED_MODULE_KEYS[:5]
    ]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(module_table=rows))
    findings = _findings_from(exc.value)
    assert any("module_table.expected_6_rows_got_5" in f for f in findings)


def test_scenarios_missing_key_reported():
    incomplete = {k: _scenario().model_dump() for k in ("base", "bullish", "bearish")}
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(scenarios=incomplete))
    findings = _findings_from(exc.value)
    assert any("scenarios.missing_keys:systemic" in f for f in findings)


def test_forward_indicators_wrong_count_reported():
    indicators = [_indicator(f"i{i}").model_dump() for i in range(3)]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(forward_indicators=indicators))
    findings = _findings_from(exc.value)
    assert any("forward_indicators.expected_5_got_3" in f for f in findings)


def test_forward_indicators_non_iso_release_date_reported():
    indicators = [_indicator(f"i{i}").model_dump() for i in range(5)]
    indicators[2]["release_date"] = "next-quarter-2026"  # >= 8 chars, not ISO
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(forward_indicators=indicators))
    findings = _findings_from(exc.value)
    assert any(
        "forward_indicators[2].release_date_not_iso_date:next-quarter-2026" in f
        for f in findings
    )


def test_boundary_notice_missing_keyword_reported():
    bad = "本回答非个股操作、非收益预测、非动态择时、非黑盒最优化。"
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(boundary_notice=bad))
    findings = _findings_from(exc.value)
    assert any(
        "boundary_notice.missing_keywords" in f and "非概率胜率" in f
        for f in findings
    )


def test_boundary_notice_all_keywords_pass():
    text = "非个股操作 非概率胜率 非收益预测 非动态择时 非黑盒最优化"
    MacroBrief.model_validate(_build_brief(boundary_notice=text))


def test_market_state_missing_etf_reported():
    cards = [
        {"symbol": s, "price": 1.0, "change_pct": 0.0, "as_of": "2026-06-28"}
        for s in ("SPY", "QQQ", "SHY")
    ]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(market_state=cards))
    findings = _findings_from(exc.value)
    assert any("market_state.missing_etfs:GLD" in f for f in findings)


def test_market_state_duplicate_etf_reported():
    cards = [
        {"symbol": s, "price": 1.0, "change_pct": 0.0, "as_of": "2026-06-28"}
        for s in ("SPY", "SPY", "QQQ", "SHY", "GLD")
    ]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(market_state=cards))
    findings = _findings_from(exc.value)
    assert any("market_state.duplicate_etf:SPY" in f for f in findings)


def test_judgment_referencing_unknown_fact_id_reported():
    judgments = [{"claim": "rates", "evidence_supports": ["f1", "ghost_id"]}]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(judgments=judgments))
    findings = _findings_from(exc.value)
    assert any(
        "judgments[0].unknown_evidence_ids:ghost_id" in f for f in findings
    )


def test_confirmed_fact_duplicate_id_reported():
    facts = [_fact("f1").model_dump(), _fact("f1").model_dump()]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(confirmed_facts=facts))
    findings = _findings_from(exc.value)
    assert any("confirmed_facts.duplicate_id:f1" in f for f in findings)


def test_confirmed_fact_unknown_source_id_reported():
    facts = [_fact("f1").model_dump()]
    facts[0]["source_id"] = "ghost_source"
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(confirmed_facts=facts))
    findings = _findings_from(exc.value)
    assert any(
        "confirmed_facts[f1].unknown_source_id:ghost_source" in f for f in findings
    )


def test_confirmed_fact_missing_evidence_ids_reported():
    facts = [_fact("f1").model_dump()]
    facts[0]["evidence_ids"] = []
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(confirmed_facts=facts))
    findings = _findings_from(exc.value)
    assert any("confirmed_facts[f1].missing_evidence_ids" in f for f in findings)


def test_unavailable_confirmed_fact_cannot_carry_value():
    facts = [_fact("f1").model_dump()]
    facts[0]["claim_status"] = "unavailable"
    facts[0]["value"] = 4.3
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(confirmed_facts=facts))
    findings = _findings_from(exc.value)
    assert any("confirmed_facts[f1].unavailable_fact_has_value" in f for f in findings)


def test_source_must_have_url_or_rag_doc_id():
    sources = [
        {"id": "s_f1", "url": None, "rag_doc_id": None, "accessed_at": "2026-06-29"}
    ]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(source_list=sources))
    findings = _findings_from(exc.value)
    assert any("source_list[s_f1].missing_url_or_rag_doc_id" in f for f in findings)


def test_source_with_rag_doc_id_only_is_valid():
    sources = [
        {"id": "s_f1", "rag_doc_id": "policy_doc_abc", "accessed_at": "2026-06-29"},
        {"id": "s_f2", "rag_doc_id": "policy_doc_def", "accessed_at": "2026-06-29"},
    ]
    MacroBrief.model_validate(_build_brief(source_list=sources))


def test_source_duplicate_id_reported():
    sources = [_source("s_f1").model_dump(), _source("s_f1").model_dump()]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(source_list=sources))
    findings = _findings_from(exc.value)
    assert any("source_list.duplicate_source_id:s_f1" in f for f in findings)


@pytest.mark.parametrize(
    "text",
    [
        "市场可能上涨 35% 的概率",
        "概率是 50%",
        "There is a 60% probability of recession",
        "probability of 25% next month",
    ],
)
def test_core_conclusion_rejects_probability_language(text):
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(core_conclusion=text))
    findings = _findings_from(exc.value)
    assert any("core_conclusion.contains_probability_language" in f for f in findings)


def test_core_conclusion_pure_percentage_without_probability_word_ok():
    text = "S&P 500 涨 0.5%,美元指数稳定。"
    MacroBrief.model_validate(_build_brief(core_conclusion=text))


def test_multiple_findings_returned_together():
    rows = [
        {"module_key": k, "module_name_zh": k, "status": "watch", "note": None}
        for k in REQUIRED_MODULE_KEYS[:5]
    ]
    bad_indicators = [_indicator(f"i{i}").model_dump() for i in range(3)]
    with pytest.raises(ValidationError) as exc:
        MacroBrief.model_validate(_build_brief(
            module_table=rows,
            forward_indicators=bad_indicators,
            boundary_notice="missing keywords here",
        ))
    findings = _findings_from(exc.value)
    assert any("module_table.missing_module_keys" in f for f in findings)
    assert any("forward_indicators.expected_5_got_3" in f for f in findings)
    assert any("boundary_notice.missing_keywords" in f for f in findings)


def test_decode_findings_returns_none_on_non_macrobrief_message():
    assert decode_findings("some random error") is None
    assert decode_findings("") is None
    assert decode_findings("macro_brief_findings_v1::not-json") is None


def test_decode_findings_round_trip():
    payload = "macro_brief_findings_v1::" + _json.dumps(["a", "b", "c"])
    assert decode_findings(payload) == ["a", "b", "c"]
