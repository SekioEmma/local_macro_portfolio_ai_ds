import json
from pathlib import Path
from types import SimpleNamespace

from app_backend.schemas.responses import DashboardEvidenceRow
from app_backend.services import ai_context_service
from app_backend.services import dashboard_service
from data_quality import macro_regime_review as d15
from data_quality import scenario_stress as d16
from modeling.metric_lookup import D15_PUBLIC_OUTPUT_KEYS, D16_PUBLIC_OUTPUT_KEYS
from modeling.model_registry import FORBIDDEN_PUBLIC_OUTPUT_KEYS

_REPO_ROOT = Path(__file__).resolve().parents[2]


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
)


def test_d15_public_output_contract_excludes_scores_and_forbidden_language():
    rows = d15.build_macro_regime_review_rows(_benign_core_rows())
    keys = {row["metric_key"] for row in rows}
    serialized = json.dumps(rows, sort_keys=True).lower()

    assert keys == set(D15_PUBLIC_OUTPUT_KEYS)
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    assert "macro_regime_score" not in serialized
    assert "support_score_internal" not in serialized
    assert "group_score_internal" not in serialized
    assert {"support_band", "evidence_quality_band", "conflict_band"} <= keys

    boundary = _by_key(rows)["interpretation_boundary"]["value"].lower()
    assert "current evidence review" in boundary
    assert "prediction model" in boundary
    assert "allocation directive" in boundary
    assert "return estimate" in boundary
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in serialized


def test_d15_hard_gates_preserve_missing_proxy_and_portfolio_boundaries():
    vix_only = d15.build_macro_regime_review_rows(
        _benign_core_rows()
        + [_row("credit_stress", "vix", 35.0, status="pressure")]
    )
    equity_only = d15.build_macro_regime_review_rows(
        _benign_core_rows()
        + [
            _row(
                "market_stress_derived",
                "sp500_drawdown_3m",
                -12.0,
                status="pressure",
                source_badge="derived",
            )
        ]
    )
    proxy_credit_only = d15.build_macro_regime_review_rows(
        _benign_core_rows(include_credit=False)
        + [
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
    blocked_credit = d15.build_macro_regime_review_rows(
        _benign_core_rows(include_credit=False)
        + [
            _row(
                "credit_stress",
                "high_yield_spread",
                6.0,
                status="pressure",
                freshness_status="stale",
            ),
            _row(
                "credit_stress",
                "credit_stress_status",
                "pressure",
                status="pressure",
                source_badge="research_needed",
            ),
        ]
    )
    portfolio_only = d15.build_macro_regime_review_rows(
        [
            _row(
                "portfolio_exposure_overlay",
                "portfolio_exposure_overlay_status",
                "available",
                status="pressure",
                source_badge="derived",
            )
        ]
    )

    assert _by_key(vix_only)["macro_regime_label"]["value"] != "credit_stress"
    assert _by_key(equity_only)["macro_regime_label"]["value"] not in {
        "credit_stress",
        "liquidity_funding_pressure",
        "stagflation_pressure",
    }
    assert _by_key(proxy_credit_only)["macro_regime_label"]["value"] != "credit_stress"
    assert _by_key(blocked_credit)["macro_regime_label"]["value"] != "credit_stress"
    assert _by_key(portfolio_only)["macro_regime_label"]["value"] == "insufficient_evidence"

    benign = _by_key(d15.build_macro_regime_review_rows(_benign_core_rows()))
    assert {"valuation", "earnings", "true_breadth"} <= set(
        benign["macro_regime_label"]["missing_inputs"]
    )
    hard_gates = benign["macro_regime_label"]["component_contributions"]["hard_gates"]
    assert hard_gates[
        "missing_stale_blocked_research_needed_insufficient_history_cannot_support_label"
    ] is True
    assert hard_gates["proxy_only_cannot_determine_pressure_high_label"] is True
    assert hard_gates["equity_drawdown_alone_cannot_trigger_stress"] is True


def test_d16_public_output_contract_excludes_probability_forecast_and_actions():
    rows = d16.build_scenario_stress_rows(_benign_core_rows())
    keys = {row["metric_key"] for row in rows}
    serialized = json.dumps(rows, sort_keys=True).lower()

    assert keys == set(D16_PUBLIC_OUTPUT_KEYS)
    assert not {
        "scenario_probability",
        "expected_return",
        "target_price",
        "stop_loss",
        "portfolio_action",
        "forecast_path",
    } & keys
    assert {
        "scenario_stress_scenarios",
        "scenario_stress_transmission_channels",
        "scenario_stress_uncertainty_band",
        "scenario_stress_missing_inputs",
        "scenario_stress_interpretation_boundary",
    } <= keys
    boundary = _by_key(rows)["scenario_stress_interpretation_boundary"]["value"].lower()
    assert "scenario matrix" in boundary
    assert "not a forecast" in boundary
    assert "event-odds model" in boundary
    assert "allocation directive" in boundary
    assert "return estimate" in boundary
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in serialized


def test_d16_scenarios_preserve_uncertainty_missing_inputs_and_proxy_limits():
    summary = d16.build_scenario_stress_summary(
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
                "market_stress_derived",
                "nasdaq100_drawdown_3m",
                -11.0,
                status="pressure",
                source_badge="derived",
            ),
        ]
    )
    concentration = next(
        item
        for item in summary["scenarios"]
        if item["scenario_name"] == "ai_mega_cap_concentration_unwind"
    )

    assert concentration["support_band"] != "strong"
    assert concentration["severity_band"] not in {"severe", "extreme"}
    assert concentration["uncertainty_band"] == "high"
    assert {"valuation", "earnings", "true_breadth"} <= set(
        concentration["missing_inputs"]
    )
    assert "valuation_earnings_true_breadth_gaps_explicit" in concentration[
        "proxy_constraints"
    ]


def test_d15_d16_enter_ai_context_only_as_model_outputs(monkeypatch):
    rows = [
        _evidence_row("macro_regime_review", "macro_regime_label", "rates_pressure"),
        _evidence_row("scenario_stress", "scenario_stress_status", "limited_evidence"),
        _evidence_row("credit_stress", "high_yield_spread", 3.4),
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
    fact_keys = {row["metric_key"] for row in manifest.included_facts}
    model_keys = {row["metric_key"] for row in manifest.included_model_outputs}
    excluded_model_keys = {row["metric_key"] for row in manifest.excluded_model_outputs}

    assert "high_yield_spread" in fact_keys
    assert "macro_regime_label" in model_keys
    assert "scenario_stress_status" in model_keys | excluded_model_keys
    assert "macro_regime_label" not in fact_keys
    assert "scenario_stress_status" not in fact_keys
    serialized = json.dumps(
        {
            "included_model_outputs": manifest.included_model_outputs,
            "excluded_model_outputs": manifest.excluded_model_outputs,
            "risk_boundaries": manifest.risk_boundaries,
        },
        sort_keys=True,
    ).lower()
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in serialized


def test_d15_d16_no_forbidden_surfaces_in_key_files():
    _FORBIDDEN_TOKENS = (
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
        "scenario_probability",
        "expected_return",
        "trade_signal",
        "target_allocation",
    )
    _AI_2_ALLOWED_IN_MAIN = {
        "DeepSeek",
        "/api/ai/deepseek",
    }

    data_quality_text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            str(_REPO_ROOT / "src/data_quality/macro_regime_review.py"),
            str(_REPO_ROOT / "src/data_quality/scenario_stress.py"),
        )
    )
    for token in _FORBIDDEN_TOKENS:
        assert token not in data_quality_text

    main_text = (_REPO_ROOT / "src/app_backend/main.py").read_text(encoding="utf-8")
    for token in _FORBIDDEN_TOKENS:
        if token in _AI_2_ALLOWED_IN_MAIN:
            continue
        assert token not in main_text


def _benign_core_rows(*, include_credit: bool = True):
    rows = [
        _row("rate_pressure", "dgs10", 4.5),
        _row("real_yield_pressure", "dfii10", 2.1),
        _row("inflation_energy_pressure", "core_cpi_yoy", 3.1),
        _row("labor_macro", "initial_jobless_claims", 230000),
        _row("labor_macro", "unemployment_rate", 4.0),
    ]
    if include_credit:
        rows.append(_row("credit_stress", "high_yield_spread", 3.4))
    return rows


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


def _evidence_row(module, metric_key, value):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value),
        unit=None,
        status="ok",
        source="local_rules",
        source_badge="derived" if module in {"macro_regime_review", "scenario_stress"} else "official",
        source_series=metric_key.upper(),
        observation_date="2026-06-01",
        generated_at="2026-06-01T00:00:00+00:00",
        freshness_status="historical",
        missing_reason=None,
        interpretation_hint="test",
        blocked_reason=None,
        ai_context_allowed=True,
        interpretation_boundary=(
            "Macro regime review is current evidence review, not future market direction."
            if module == "macro_regime_review"
            else "Scenario stress is a hypothetical scenario matrix, not future market direction."
        ),
        ai_context_tier="model_output" if module in {"macro_regime_review", "scenario_stress"} else None,
        trigger_eligibility="reference_review_only",
    )


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}
