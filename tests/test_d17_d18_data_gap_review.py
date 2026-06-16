import json
from pathlib import Path
from types import SimpleNamespace

from app_backend.schemas.responses import DashboardEvidenceRow
from app_backend.services import ai_context_service
from app_backend.services import dashboard_service
from data_quality import growth_inflation_macro_pack as d17
from data_quality import valuation_equity_structure as d18
from modeling.metric_lookup import (
    D17_PUBLIC_OUTPUT_KEYS,
    D18_PUBLIC_OUTPUT_KEYS,
)
from modeling.model_registry import FORBIDDEN_PUBLIC_OUTPUT_KEYS


FORBIDDEN_OUTPUT_PHRASES = (
    "crash probability",
    "recession probability",
    "market direction probability",
    "expected return",
    "predicted return",
    "future return",
    "trade signal",
    "target allocation",
    "target price",
    "stop loss",
    "portfolio action",
    "forecast path",
    "timing signal",
    "will rise",
    "will fall",
)


# ---------------------------------------------------------------------------
# 5.1 D17 public output contract
# ---------------------------------------------------------------------------


def test_d17_public_output_contract_excludes_forbidden_keys_and_language():
    rows = d17.build_growth_inflation_macro_pack_rows(_d17_benign_rows())
    keys = {row["metric_key"] for row in rows}
    serialized = json.dumps(rows, sort_keys=True).lower()

    assert keys == set(D17_PUBLIC_OUTPUT_KEYS)
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in serialized

    boundary = _by_key(rows)["growth_macro_interpretation_boundary"]["value"].lower()
    assert "context layer" in boundary
    assert "not a forecast" in boundary
    assert "return estimate" in boundary
    assert "allocation directive" in boundary


def test_d17_missing_growth_pack_areas_remain_visible():
    rows = d17.build_growth_inflation_macro_pack_rows([])
    by_key = _by_key(rows)
    missing_text = by_key["growth_macro_missing_inputs"]["value"]

    for expected in (
        "ism_manufacturing_pmi",
        "ism_services_pmi",
        "retail_sales_mom",
        "industrial_production_yoy",
        "housing_starts",
        "mortgage_30y_rate",
    ):
        assert expected in missing_text

    assert by_key["growth_macro_missing_inputs"]["status"] == "research_needed"
    assert by_key["growth_macro_missing_inputs"]["ai_context_allowed"] is False
    assert by_key["growth_macro_status"]["status"] == "research_needed"


def test_d17_does_not_treat_missing_or_research_needed_as_support():
    rows = d17.build_growth_inflation_macro_pack_rows([])
    research_rows = [row for row in rows if row["status"] == "research_needed"]
    assert research_rows
    for row in research_rows:
        assert row["ai_context_allowed"] is False


# ---------------------------------------------------------------------------
# 5.2 D17 low-frequency and source boundaries
# ---------------------------------------------------------------------------


def test_d17_oil_alone_cannot_confirm_inflation_loss_of_control():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [_row("inflation_energy_pressure", "wti_30d_change", 9.0, status="pressure")]
    )

    assert summary["inflation"]["status"] != "pressure"
    assert (
        summary["inflation"]["hard_gates"][
            "oil_alone_cannot_trigger_inflation_pressure"
        ]
        is True
    )


def test_d17_single_labor_row_cannot_confirm_broad_growth_slowdown():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [
            _row(
                "labor_macro",
                "labor_deterioration_status",
                "watch",
                status="watch",
            )
        ]
    )

    assert summary["growth"]["status"] != "pressure"
    assert (
        summary["growth"]["hard_gates"]["labor_watch_alone_not_business_cycle_call"]
        is True
    )
    assert summary["growth"]["hard_gates"][
        "broad_growth_pack_missing_until_source_gated"
    ] is True


def test_d17_cpi_alone_cannot_confirm_stagflation_pressure():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [
            _row(
                "inflation_energy_pressure",
                "core_cpi_yoy",
                "pressure",
                status="pressure",
            )
        ]
    )

    assert summary["stagflation"]["status"] != "pressure"
    assert (
        summary["stagflation"]["hard_gates"][
            "cpi_alone_cannot_trigger_stagflation_watch_pressure"
        ]
        is True
    )


def test_d17_sahm_rule_proxy_is_not_a_recession_trigger():
    # The Sahm rule proxy is not part of D17 production keys. D17 must not
    # claim recession even if a Sahm-style proxy row is present.
    summary = d17.build_growth_inflation_macro_pack_summary(
        [
            _row(
                "labor_macro",
                "sahm_rule_proxy_status",
                "pressure",
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            )
        ]
    )
    serialized = json.dumps(summary, ensure_ascii=False, sort_keys=True).lower()

    assert "recession" not in serialized
    assert summary["growth"]["status"] in {"research_needed", "ok", "watch"}
    assert summary["growth"]["status"] != "pressure"


def test_d17_low_frequency_inflation_boundary_is_visible_when_core_supplied():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [
            _row(
                "inflation_energy_pressure",
                "core_cpi_yoy",
                "ok",
                status="ok",
            )
        ]
    )

    assert (
        summary["inflation"]["hard_gates"]["low_frequency_inflation_data_boundary"]
        is True
    )


# ---------------------------------------------------------------------------
# 5.3 D18 public output contract
# ---------------------------------------------------------------------------


def test_d18_public_output_contract_excludes_forbidden_keys_and_language():
    rows = d18.build_valuation_equity_structure_rows(
        [
            _row(
                "valuation_research",
                "sp500_trailing_pe",
                "pressure",
                status="pressure",
                source_badge="derived",
            )
        ]
    )
    keys = {row["metric_key"] for row in rows}
    serialized = json.dumps(rows, sort_keys=True).lower()

    assert keys == set(D18_PUBLIC_OUTPUT_KEYS)
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in serialized

    boundary = _by_key(rows)["valuation_interpretation_boundary"]["value"].lower()
    assert "research/proxy context" in boundary
    assert "not a forecast" in boundary
    assert "timing model" in boundary
    assert "return estimate" in boundary
    assert "proxy breadth" in boundary


def test_d18_keeps_valuation_earnings_and_true_breadth_gaps_visible():
    rows = d18.build_valuation_equity_structure_rows([])
    by_key = _by_key(rows)

    assert by_key["valuation_context_status"]["value"] == "research_needed"
    assert by_key["earnings_context_status"]["value"] == "research_needed"
    assert (
        by_key["breadth_concentration_context_status"]["value"] == "research_needed"
    )

    valuation_missing = by_key["valuation_missing_inputs"]["value"]
    for token in (
        "sp500_forward_pe_source_gate",
        "sp500_cape_source_gate",
        "sp500_erp_source_gate",
    ):
        assert token in valuation_missing

    earnings_missing = by_key["earnings_missing_inputs"]["value"]
    for token in ("earnings_revision_source_gate", "eps_growth_source_gate"):
        assert token in earnings_missing

    breadth_missing = by_key["breadth_concentration_missing_inputs"]["value"]
    for token in ("true_breadth_source_gate", "constituent_breadth_source_gate"):
        assert token in breadth_missing

    for key in (
        "valuation_missing_inputs",
        "earnings_missing_inputs",
        "breadth_concentration_missing_inputs",
        "equity_structure_missing_inputs",
    ):
        assert by_key[key]["status"] == "research_needed"
        assert by_key[key]["ai_context_allowed"] is False


# ---------------------------------------------------------------------------
# 5.4 D18 proxy / source boundaries
# ---------------------------------------------------------------------------


def test_d18_proxy_only_cannot_confirm_valuation_or_breadth_label():
    # forward PE delivered via a proxy badge must not pass the source gate.
    rows = d18.build_valuation_equity_structure_rows(
        [
            _row(
                "valuation_research",
                "sp500_forward_pe",
                "pressure",
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            )
        ]
    )
    by_key = _by_key(rows)

    assert by_key["valuation_context_status"]["value"] == "research_needed"
    assert by_key["valuation_pressure_hint"]["value"] == "research_needed"
    assert (
        by_key["valuation_metric_source_quality"]["value"]
        == "source_gated_inputs_missing"
    )
    assert by_key["valuation_context_status"]["ai_context_allowed"] is False


def test_d18_single_proxy_cannot_create_breadth_or_structure_pressure():
    summary = d18.build_valuation_equity_structure_summary(
        [
            _row(
                "breadth_concentration_proxy",
                "qqq_vs_spy_30d",
                -4.0,
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            )
        ]
    )

    breadth = summary["breadth_concentration"]
    assert breadth["status"] == "limited_proxy_context"
    assert breadth["hard_gates"]["single_proxy_cannot_create_pressure"] is True
    assert breadth["hard_gates"]["proxy_breadth_does_not_replace_true_breadth"] is True

    structure = summary["equity_structure"]
    assert structure["status"] == "limited_proxy_context"
    assert structure["hard_gates"]["single_proxy_cannot_create_pressure"] is True


def test_d18_two_proxies_only_reach_proxy_pressure_with_gates_intact():
    summary = d18.build_valuation_equity_structure_summary(
        [
            _row(
                "breadth_concentration_proxy",
                "qqq_vs_spy_30d",
                -4.0,
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            ),
            _row(
                "breadth_concentration_proxy",
                "spy_vs_rsp_30d",
                -3.0,
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            ),
        ]
    )

    breadth = summary["breadth_concentration"]
    assert breadth["status"] == "pressure"
    assert breadth["hard_gates"]["spy_rsp_qqq_proxy_auxiliary_only"] is True
    assert breadth["hard_gates"]["proxy_breadth_does_not_replace_true_breadth"] is True

    # True breadth and valuation gaps must remain visible even when proxies
    # escalate, so the user cannot mistake proxy concentration for true breadth.
    for token in ("true_breadth_source_gate", "constituent_breadth_source_gate"):
        assert token in summary["missing_inputs"]


def test_d18_hyg_lqd_proxy_does_not_enter_valuation_breadth_or_structure():
    summary = d18.build_valuation_equity_structure_summary(
        [
            _row(
                "breadth_concentration_proxy",
                "hyg_vs_lqd_30d",
                -4.0,
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            )
        ]
    )

    assert summary["valuation"]["status"] == "research_needed"
    assert summary["earnings"]["status"] == "research_needed"
    assert summary["breadth_concentration"]["status"] == "research_needed"
    assert summary["equity_structure"]["status"] == "unavailable"


def test_d18_source_gated_valuation_promotes_only_when_source_badge_qualifies():
    rows = d18.build_valuation_equity_structure_rows(
        [
            _row(
                "valuation_research",
                "sp500_forward_pe",
                "pressure",
                status="pressure",
                source_badge="derived",
            )
        ]
    )
    by_key = _by_key(rows)

    assert by_key["valuation_context_status"]["value"] == "available"
    assert by_key["valuation_pressure_hint"]["value"] == "elevated"
    assert by_key["valuation_metric_source_quality"]["value"] == "source_gated"
    # Missing inputs remain explicit even when one valuation fact is gated.
    valuation_missing = by_key["valuation_missing_inputs"]["value"]
    for token in (
        "sp500_cape_source_gate",
        "sp500_erp_source_gate",
        "sp500_top10_weight_source_gate",
    ):
        assert token in valuation_missing


# ---------------------------------------------------------------------------
# 5.5 AI Context / Golden Contract
# ---------------------------------------------------------------------------


def test_d17_d18_enter_ai_context_only_when_eligible(monkeypatch):
    rows = [
        _evidence_row(
            "growth_inflation_macro_pack",
            "growth_macro_status",
            "ok",
            ai_context_allowed=True,
            tier="fact_or_excluded_by_row",
        ),
        _evidence_row(
            "growth_inflation_macro_pack",
            "growth_macro_missing_inputs",
            "ism_manufacturing_pmi",
            ai_context_allowed=False,
            tier="fact_or_excluded_by_row",
            status="research_needed",
        ),
        _evidence_row(
            "valuation_equity_structure",
            "valuation_context_status",
            "research_needed",
            ai_context_allowed=False,
            tier="fact_or_excluded_by_row",
            status="research_needed",
        ),
        _evidence_row(
            "valuation_equity_structure",
            "breadth_concentration_context_status",
            "limited_proxy_context",
            ai_context_allowed=True,
            tier="fact_or_excluded_by_row",
        ),
    ]
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: SimpleNamespace(
            generated_at="2026-06-01T00:00:00+00:00",
            rows=rows,
        ),
    )

    manifest = ai_context_service.build_ai_context_manifest()
    included_keys = {
        row["metric_key"] for row in manifest.included_facts
    } | {row["metric_key"] for row in manifest.included_model_outputs}
    excluded_keys = {
        row["metric_key"] for row in manifest.excluded_facts
    } | {row["metric_key"] for row in manifest.excluded_model_outputs}

    assert "growth_macro_status" in included_keys
    assert "breadth_concentration_context_status" in included_keys
    assert "growth_macro_missing_inputs" not in included_keys
    assert "valuation_context_status" not in included_keys
    assert "growth_macro_missing_inputs" in excluded_keys
    assert "valuation_context_status" in excluded_keys


def test_d17_d18_model_output_preserves_interpretation_boundaries():
    d17_rows = d17.build_growth_inflation_macro_pack_rows(_d17_benign_rows())
    d18_rows = d18.build_valuation_equity_structure_rows(
        [
            _row(
                "valuation_research",
                "sp500_trailing_pe",
                "watch",
                status="watch",
                source_badge="derived",
            )
        ]
    )

    for rows, key in (
        (d17_rows, "growth_macro_interpretation_boundary"),
        (d17_rows, "inflation_macro_interpretation_boundary"),
        (d17_rows, "policy_constraint_interpretation_boundary"),
        (d17_rows, "stagflation_watch_interpretation_boundary"),
        (d18_rows, "valuation_interpretation_boundary"),
        (d18_rows, "earnings_interpretation_boundary"),
        (d18_rows, "equity_structure_interpretation_boundary"),
        (d18_rows, "breadth_concentration_interpretation_boundary"),
    ):
        boundary = _by_key(rows)[key]["value"].lower()
        assert "not a forecast" in boundary
        assert "return estimate" in boundary
        assert "allocation directive" in boundary


def test_d17_d18_public_keys_match_registry_and_exclude_forbidden_keys():
    d17_rows = d17.build_growth_inflation_macro_pack_rows([])
    d18_rows = d18.build_valuation_equity_structure_rows([])

    d17_keys = {row["metric_key"] for row in d17_rows}
    d18_keys = {row["metric_key"] for row in d18_rows}

    assert d17_keys == set(D17_PUBLIC_OUTPUT_KEYS)
    assert d18_keys == set(D18_PUBLIC_OUTPUT_KEYS)
    assert not ((d17_keys | d18_keys) & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))


# ---------------------------------------------------------------------------
# 5.6 No forbidden surfaces
# ---------------------------------------------------------------------------


def test_d17_d18_production_files_have_no_forbidden_surfaces():
    paths = (
        "src/data_quality/growth_inflation_macro_pack.py",
        "src/data_quality/valuation_equity_structure.py",
        "src/app_backend/main.py",
    )
    text = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)

    for token in (
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/external",
        "DeepSeek",
        "Tavily",
        "external_llm.yaml",
        ".env",
        "crash_probability",
        "recession_probability",
        "market_direction_probability",
        "expected_return",
        "predicted_return",
        "future_return",
        "target_price",
        "trade_signal",
        "target_allocation",
        "forward_pe_provider",
        "cape_scraper",
        "earnings_revision_scraper",
    ):
        assert token not in text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _d17_benign_rows():
    return [
        _row("inflation_energy_pressure", "core_cpi_yoy", "ok", status="ok"),
        _row("inflation_energy_pressure", "core_pce_yoy", "ok", status="ok"),
        _row("rate_pressure", "dgs10", 4.4),
        _row("real_yield_pressure", "dfii10", 2.0),
        _row("labor_macro", "unemployment_rate", 4.0),
        _row("labor_macro", "initial_jobless_claims", 230000),
    ]


def _row(
    module,
    metric_key,
    value,
    *,
    status="ok",
    source_badge="official",
    freshness_status="fresh",
    trigger_eligibility="reference_review_only",
):
    return {
        "row_id": f"{module}:{metric_key}",
        "module": module,
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value,
        "value_text": str(value),
        "unit": None,
        "status": status,
        "source": "test_source",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": freshness_status,
        "missing_reason": None,
        "interpretation_hint": "test evidence",
        "interpretation_boundary": "Reference evidence only.",
        "blocked_reason": None,
        "ai_context_allowed": True,
        "trigger_eligibility": trigger_eligibility,
    }


def _evidence_row(
    module,
    metric_key,
    value,
    *,
    ai_context_allowed: bool = True,
    tier: str = "fact_or_excluded_by_row",
    status: str = "ok",
):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value),
        unit=None,
        status=status,
        source="local_rules",
        source_badge="derived",
        source_series=metric_key.upper(),
        observation_date="2026-06-01",
        generated_at="2026-06-01T00:00:00+00:00",
        freshness_status="historical",
        missing_reason=None if ai_context_allowed else status,
        interpretation_hint="test",
        blocked_reason=None,
        ai_context_allowed=ai_context_allowed,
        interpretation_boundary=(
            "Growth/inflation macro pack is a conservative current-evidence "
            "context layer. It is not a forecast, business-cycle call, "
            "event-odds model, allocation directive, or return estimate."
            if module == "growth_inflation_macro_pack"
            else "Valuation/equity structure is a conservative research/proxy "
            "context layer. It is not a forecast, timing model, event-odds "
            "model, allocation directive, or return estimate. Proxy "
            "breadth/concentration does not replace true breadth."
        ),
        ai_context_tier=tier,
        trigger_eligibility="auxiliary_only",
    )


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}
