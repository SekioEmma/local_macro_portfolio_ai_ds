import json
import socket
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app_backend.schemas.responses import DashboardEvidenceRow
from app_backend.main import app
from app_backend.services import ai_context_service
from app_backend.services import dashboard_service


def test_ai_context_manifest_includes_and_excludes_expected_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/ai/context-preview")

    assert response.status_code == 200
    data = response.json()
    included_keys = {row["metric_key"] for row in data["included_facts"]}
    excluded = {row["metric_key"]: row for row in data["excluded_facts"]}
    model_keys = {row["metric_key"] for row in data["included_model_outputs"]}
    excluded_model_keys = {
        row["metric_key"] for row in data["excluded_model_outputs"]
    }

    assert "high_yield_spread" in included_keys
    assert "vix" in included_keys
    assert "dgs30_breakout_confirmed" in excluded
    assert excluded["dgs30_breakout_confirmed"]["excluded_reason"] in {
        "status_research_needed",
        "source_badge_research_needed",
    }
    assert "financial_stress_score" in model_keys
    assert "pullback_classification" in model_keys
    assert "macro_regime_label" in model_keys
    assert "scenario_stress_status" in model_keys | excluded_model_keys
    assert "valuation_context_status" in included_keys | set(excluded)
    assert "valuation_missing_inputs" in excluded
    assert "financial_stress_score" not in included_keys
    assert "pullback_classification" not in included_keys
    assert "macro_regime_label" not in included_keys


def test_model_outputs_preserve_derived_badge_and_boundaries(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/context/manifest").json()
    stress = _model_output(data, "financial_stress_score")
    pullback = _model_output(data, "pullback_classification")
    regime = _model_output(data, "macro_regime_label")

    assert stress["source_badge"] == "derived"
    assert "pressure temperature" in stress["interpretation_boundary"]
    assert stress["input_evidence"]
    assert pullback["source_badge"] == "derived"
    assert "current evidence review" in pullback["interpretation_boundary"]
    assert pullback["input_evidence"]
    assert regime["source_badge"] == "derived"
    assert "current evidence review" in regime["interpretation_boundary"]
    assert "macro_regime_score" not in json.dumps(regime)


def test_proxy_rows_keep_proxy_badge_and_search_is_excluded(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/ai/context-preview").json()
    proxy_or_derived_rows = [
        row
        for row in data["included_facts"]
        if row["source_badge"] in {"proxy", "derived"}
    ]

    assert proxy_or_derived_rows
    assert all(row["source_badge"] != "official" for row in proxy_or_derived_rows)
    assert data["search_policy"]["search_enabled"] is False
    assert data["search_policy"]["search_derived_default"] == "excluded"


def test_portfolio_policy_excludes_holdings_line_items(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/ai/context-preview").text
    data = json.loads(body)

    assert data["portfolio_context_policy"]["mode"] == "compact_summary_only"
    assert data["portfolio_context_policy"]["holdings_line_items_allowed"] is False
    assert "max_deviation_pp" in (
        data["portfolio_context_policy"]["included_portfolio_metric_keys"]
        + data["portfolio_context_policy"]["excluded_portfolio_metric_keys"]
    )
    assert "RAW_FUND" not in body
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in body


def test_manifest_does_not_leak_private_payloads_or_credentials(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/ai/context-preview").text.lower()

    assert "sk-" not in body
    assert "api_key" not in body
    assert "deepseek_api_key" not in body
    assert "tavily_api_key" not in body
    assert ("raw_" + "prompt") not in body
    assert ("raw_" + "provider") not in body
    assert ("raw_" + "holdings") not in body
    assert "must_not_leak" not in body


def test_manifest_risk_boundaries_are_complete(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/ai/context-preview").json()

    assert data["risk_boundaries"] == [
        "Reference evidence only.",
        "No event-odds model.",
        "No business-cycle call.",
        "VIX alone is not systemic crisis.",
        "Equity drawdown alone is not systemic crisis.",
        "Proxy breadth is not true breadth.",
        "Financial stress score is pressure temperature, not prediction.",
        "Pullback checklist is risk review, not forecast.",
        "Portfolio deviation cannot be attributed to macro factors.",
        "Liquidity/funding stress rows are reference evidence, not allocation directives.",
        "Official stress indices do not replace the project financial stress composite.",
        "Commercial paper spread cannot alone prove systemic crisis.",
        "ON RRP usage alone is not a risk trigger.",
        "Macro regime review is current evidence review, not future market direction.",
        "Macro regime review produces no probability or allocation directive.",
        "Historical validation is event-window replay, not future market direction.",
        "Historical validation produces no event odds or allocation directive.",
        "Scenario stress is a hypothetical scenario matrix, not future market direction.",
        "Scenario stress produces no event odds or allocation directive.",
        "Valuation/equity structure is research/proxy context; valuation alone cannot determine regime or systemic review.",
    ]


def test_manifest_carries_eligible_d13_and_excludes_insufficient_history(monkeypatch):
    rows = [
        _evidence_row(
            "historical_risk_percentile",
            "vix_percentile",
            95.0,
            status="stress",
            ai_context_allowed=True,
            percentile_band="extreme",
            robust_zscore_band="high",
        ),
        _evidence_row(
            "historical_risk_percentile",
            "high_yield_spread_percentile",
            None,
            status="insufficient_history",
            ai_context_allowed=False,
            percentile_band=None,
            freshness_status="insufficient_history",
            missing_reason="insufficient_history_for_percentile",
        ),
        _evidence_row(
            "financial_stress_composite",
            "financial_stress_score",
            10.0,
            source_badge="derived",
            component_contributions={
                "percentile_context": {
                    "available": [
                        {
                            "metric_key": "vix_percentile",
                            "source_badge": "derived",
                            "lookback_window": "5Y rolling",
                            "percentile_band": "extreme",
                            "trigger_eligibility": "auxiliary_only",
                            "interpretation_boundary": "not a forecast",
                        }
                    ]
                }
            },
        ),
    ]
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
    )

    manifest = ai_context_service.build_ai_context_manifest()
    included_d13 = [row for row in manifest.included_facts if row["metric_key"] == "vix_percentile"]
    excluded_d13 = [
        row
        for row in manifest.excluded_facts
        if row["metric_key"] == "high_yield_spread_percentile"
    ]
    stress = _model_output({"included_model_outputs": manifest.included_model_outputs}, "financial_stress_score")

    assert included_d13
    assert included_d13[0]["source_badge"] == "derived"
    assert included_d13[0]["lookback_window"] == "5Y rolling"
    assert included_d13[0]["percentile_band"] == "extreme"
    assert included_d13[0]["robust_zscore_band"] == "high"
    assert included_d13[0]["trigger_eligibility"] == "auxiliary_only"
    assert excluded_d13[0]["excluded_reason"] == "status_insufficient_history"
    assert "percentile_context" in stress["component_contributions"]


def test_manifest_carries_d10_d11_liquidity_context(monkeypatch):
    liquidity_context = {
        "available": [
            {
                "metric_key": "liquidity_funding_stress_status",
                "value": "ok",
                "status": "ok",
                "source_badge": "derived",
                "source_series": "liquidity_funding_stress_status",
                "observation_date": "2026-06-01",
                "interpretation_boundary": "Liquidity/funding stress rows are reference evidence, not allocation directives.",
            }
        ],
        "available_count": 1,
        "status": "ok",
        "d14_used_as_confirmation_only": True,
    }
    rows = [
        _evidence_row(
            "financial_stress_composite",
            "financial_stress_score",
            10.0,
            source_badge="derived",
            component_contributions={"funding_liquidity": liquidity_context},
        ),
        _evidence_row(
            "pullback_systemic_risk_checklist",
            "pullback_classification",
            "ordinary_pullback",
            source_badge="derived",
            component_contributions={"pullback_liquidity_funding_context": liquidity_context},
        ),
    ]
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
    )

    manifest = ai_context_service.build_ai_context_manifest()
    stress = _model_output({"included_model_outputs": manifest.included_model_outputs}, "financial_stress_score")
    pullback = _model_output({"included_model_outputs": manifest.included_model_outputs}, "pullback_classification")

    assert "funding_liquidity" in stress["component_contributions"]
    assert "pullback_liquidity_funding_context" in pullback["component_contributions"]
    body = json.dumps(manifest.source_summary)
    assert "raw_provider" not in body


def _model_output(data, metric_key):
    for row in data["included_model_outputs"]:
        if row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing model output {metric_key}")


def _evidence_row(
    module,
    metric_key,
    value,
    *,
    status="ok",
    source_badge="derived",
    ai_context_allowed=True,
    percentile_band=None,
    robust_zscore_band=None,
    freshness_status="historical",
    missing_reason=None,
    component_contributions=None,
):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value) if value is not None else "insufficient history",
        unit=None,
        status=status,
        source="local_market_history",
        source_badge=source_badge,
        source_series=metric_key.upper(),
        observation_date="2026-06-01",
        generated_at="2026-06-01T00:00:00+00:00",
        freshness_status=freshness_status,
        missing_reason=missing_reason,
        interpretation_hint="test",
        blocked_reason=None if ai_context_allowed else f"status_{status}",
        ai_context_allowed=ai_context_allowed,
        component_contributions=component_contributions,
        interpretation_boundary="Historical percentile is relative to local history, not a forecast.",
        lookback_window="5Y rolling" if module == "historical_risk_percentile" else None,
        observation_count=1200 if module == "historical_risk_percentile" else None,
        minimum_observation_count=60 if module == "historical_risk_percentile" else None,
        history_quality_status="sufficient" if ai_context_allowed else "insufficient_history",
        percentile_band=percentile_band,
        robust_zscore_band=robust_zscore_band,
        trigger_eligibility="auxiliary_only" if ai_context_allowed else "not_eligible",
    )


def _write_reports(tmp_path):
    generated_at = "2026-01-01T00:00:00+00:00"

    def metric(value, source="FRED", badge="official", status="ok"):
        return {
            "value": value,
            "status": status,
            "source": source,
            "source_badge": badge,
            "observation_date": "2026-01-01",
            "freshness_status": "fresh",
        }

    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "risk_level": "watch",
                "high_yield_spread": metric(3.4),
                "investment_grade_spread": metric(1.2),
                "vix": metric(18.2, source="CBOE"),
                "credit_stress_status": metric("watch"),
                "dgs10": metric(4.52),
                "dgs30": metric(4.83),
                "dfii10": metric(2.1),
                "t10yie": metric(2.35),
                "real_yield_pressure_status": metric("pressure"),
                "core_cpi_yoy": metric(3.1),
                "core_pce_yoy": metric(2.8),
                "ppiaco_yoy": metric(1.7),
                "unemployment_rate": metric(4.0),
                "initial_jobless_claims": metric(230000),
                "hyg_vs_lqd_30d": metric(-1.2, source="yfinance", badge="proxy"),
                "llm_context_pack": {"raw": "must_not_leak"},
                "raw_extra": "must_not_leak",
                "raw_" + "prompt": "must_not_leak",
                "raw_" + "provider_response": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "max_deviation_asset": {"value": "equity", "status": "ok"},
                "max_deviation_pp": {"value": 2.3, "status": "ok"},
                "equity_total_deviation_pp": {"value": 1.4, "status": "ok"},
                "cash_reserve_status": {"value": "available", "status": "ok"},
                "holdings_updated_at": {"value": "2026-01-01", "status": "ok"},
                "holdings": [
                    {
                        "ticker": "RAW_FUND",
                        "amount": "HOLDINGS_AMOUNT_MUST_NOT_LEAK",
                    }
                ],
                "raw_extra": "must_not_leak",
                "raw_" + "holdings": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in manifest tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
