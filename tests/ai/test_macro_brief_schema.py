from __future__ import annotations

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
)


def _etf_card(symbol: str = "SPY") -> ETFStateCard:
    return ETFStateCard(symbol=symbol, price=400.0, change_pct=0.5, as_of="2026-06-28")


def _fact(idx: str = "f1") -> ConfirmedFact:
    return ConfirmedFact(
        id=idx, statement="dgs10 was 4.30", value=4.30, unit="%",
        source_id=f"s_{idx}", as_of="2026-06-27",
    )


def _judgment(supports: list[str] | None = None) -> Judgment:
    return Judgment(claim="rates remain elevated", evidence_supports=supports or ["f1"])


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
        "judgments": [{"claim": "x", "evidence_supports": ["f1"]}],
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
        "source_list": [_source().model_dump()],
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
