from pathlib import Path

import pytest

from app_backend.schemas.responses import DashboardMetric
from app_backend.services import (
    dashboard_derived_metrics,
    dashboard_historical_derived,
    dashboard_key_metrics,
    dashboard_metric_builder,
    dashboard_metric_catalog,
    dashboard_portfolio_compact,
    dashboard_service,
)
from app_backend.services.dashboard_report_loader import ReportState
from data_quality import historical_derived_metrics


def test_dashboard_metric_builder_module_has_no_reverse_import():
    for module in (
        dashboard_metric_builder,
        dashboard_historical_derived,
        dashboard_portfolio_compact,
        dashboard_derived_metrics,
        dashboard_metric_catalog,
        dashboard_key_metrics,
    ):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "dashboard_service" not in source


def test_dashboard_metric_builder_reexport_surface_characterization():
    assert dashboard_service._format_value is dashboard_metric_builder.format_value
    assert dashboard_service._metric_status is dashboard_metric_builder.metric_status
    assert dashboard_service._metric_freshness is dashboard_metric_builder.metric_freshness
    assert dashboard_service._build_metric is not dashboard_metric_builder.build_metric
    assert (
        dashboard_service.INDEX_LEVEL_YOY_MISSING_REASON
        == dashboard_metric_builder.INDEX_LEVEL_YOY_MISSING_REASON
    )
    assert dashboard_service.SOURCE_BADGE_ALIASES == dashboard_metric_builder.SOURCE_BADGE_ALIASES
    assert dashboard_service.INFLATION_YOY_METRIC_KEYS == dashboard_metric_builder.INFLATION_YOY_METRIC_KEYS
    assert dashboard_service.METRIC_SPECS is dashboard_metric_catalog.METRIC_SPECS
    assert dashboard_service.CORE_METRIC_KEYS is dashboard_metric_catalog.CORE_METRIC_KEYS
    assert dashboard_service._historical_derived_metric is dashboard_historical_derived.historical_derived_metric
    assert dashboard_service._portfolio_compact_metric is dashboard_portfolio_compact.portfolio_compact_metric
    assert dashboard_service._credit_status_from_values is dashboard_derived_metrics.credit_status_from_values
    assert dashboard_service._key_metrics_for_module is not dashboard_key_metrics.key_metrics_for_module


def test_build_metric_missing_official_macro_metric_characterization():
    spec = _spec("ppi_final_demand_yoy", missing_status="insufficient_history")

    metric = dashboard_service._build_metric(
        "inflation_energy_pressure",
        (report("market_snapshot", {"generated_at": "2026-01-01T00:00:00+00:00"}),),
        spec,
    )

    assert metric.metric_key == "ppi_final_demand_yoy"
    assert metric.status == "insufficient_history"
    assert metric.source == "FRED"
    assert metric.source_badge == "missing"
    assert metric.source_series is None
    assert metric.missing_reason == (
        "PPI final demand YoY requires at least 13 monthly PPIFIS observations; "
        "do not use index level as YoY."
    )
    assert metric.ai_context_allowed is False
    assert metric.value is None
    assert metric.value_text == "insufficient history"


def test_ppi_final_demand_and_ppiaco_boundary_characterization():
    reports = (
        report(
            "market_snapshot",
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "ppiaco_yoy": _payload(2.4, source_series="PPIACO"),
                "ppi_final_demand": _payload(
                    157.7,
                    source_series="PPIFIS",
                    unit="index",
                ),
                "ppi_final_demand_yoy": _payload(
                    157.7,
                    source_series="PPIFIS",
                    unit="index",
                ),
            },
        ),
    )

    ppiaco = dashboard_service._build_metric(
        "inflation_energy_pressure",
        reports,
        _spec("ppiaco_yoy", format_kind="signed_percent"),
    )
    index = dashboard_service._build_metric(
        "inflation_energy_pressure",
        reports,
        _spec("ppi_final_demand", unit="index", format_kind="number"),
    )
    yoy = dashboard_service._build_metric(
        "inflation_energy_pressure",
        reports,
        _spec("ppi_final_demand_yoy", format_kind="signed_percent", missing_status="insufficient_history"),
    )

    assert "not final demand PPI" in ppiaco.interpretation_hint
    assert ppiaco.source_series == "PPIACO"
    assert index.metric_key == "ppi_final_demand"
    assert index.source_series == "PPIFIS"
    assert index.value == 157.7
    assert yoy.status == "insufficient_history"
    assert yoy.value is None
    assert yoy.value_text == "insufficient history"
    assert yoy.missing_reason == dashboard_service.INDEX_LEVEL_YOY_MISSING_REASON
    assert yoy.ai_context_allowed is False


def test_stale_data_escalation_characterization():
    reports = (
        report(
            "market_snapshot",
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "dgs10": _payload(4.25, freshness_status="stale"),
            },
        ),
    )

    metric = dashboard_service._build_metric("rate_pressure", reports, _spec("dgs10"))

    assert metric.status == "stale"
    assert metric.freshness_status == "stale"
    assert metric.ai_context_allowed is False
    assert metric.value_text == "4.25%"
    assert metric.missing_reason is None


@pytest.mark.parametrize(
    ("badge", "expected"),
    [
        ("official", "official"),
        ("official_fallback", "official_fallback"),
        ("official_reference", "official_reference"),
        ("scraped_official_reference", "scraped_official_reference"),
        ("commercial_api_fallback", "commercial_api_fallback"),
        ("unofficial_fallback", "unofficial_fallback"),
        ("proxy", "proxy"),
        ("search-derived", "search-derived"),
        ("unknown_badge", "missing"),
        ("official_api", "official"),
        ("third_party_api", "proxy"),
    ],
)
def test_source_badge_normalization_characterization(badge, expected):
    metric = dashboard_service._build_metric(
        "rate_pressure",
        (report("market_snapshot", {"custom_metric": _payload(10, source_badge=badge)}),),
        _spec("custom_metric", unit=None, format_kind="number"),
    )

    assert metric.source_badge == expected


def test_source_badge_portfolio_local_and_derived_characterization():
    portfolio = dashboard_service._build_metric(
        "portfolio_deviation",
        (report("portfolio_snapshot", {"custom_metric": _payload(10, source_badge="official")}),),
        _spec("custom_metric", unit=None, format_kind="number"),
    )
    derived = dashboard_service._build_metric(
        "rate_pressure",
        (
            report(
                "market_snapshot",
                {"dgs10_5d_avg": _payload(4.2, source_badge="official", source_series="DGS10")},
            ),
        ),
        _spec("dgs10_5d_avg"),
    )

    assert portfolio.source_badge == "local"
    assert portfolio.source == "FRED"
    assert derived.source_badge == "derived"


def test_quality_metadata_priority_characterization():
    reports = (
        report(
            "market_snapshot",
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "source": "report-source",
                "source_badge": "proxy",
                "data_quality": {
                    "market_data_quality": {
                        "dgs10": {
                            "source": "quality-source",
                            "source_badge": "official",
                            "source_series": "DGS10",
                            "freshness_status": "fresh",
                            "observation_date": "2026-01-02",
                        }
                    }
                },
                "dgs10": {"value": 4.2, "status": "ok"},
            },
        ),
    )

    metric = dashboard_service._build_metric("rate_pressure", reports, _spec("dgs10"))

    assert metric.source == "quality-source"
    assert metric.source_badge == "official"
    assert metric.source_series == "DGS10"
    assert metric.freshness_status == "fresh"
    assert metric.observation_date == "2026-01-02"


def test_portfolio_holdings_updated_at_quality_metadata_characterization():
    metric = dashboard_service._build_metric(
        "portfolio_deviation",
        (
            report(
                "portfolio_snapshot",
                {
                    "generated_at": "2026-01-03T00:00:00+00:00",
                    "holdings_updated_at": "2026-01-02",
                    "holdings_freshness_status": "fresh",
                },
            ),
        ),
        _spec("holdings_updated_at", unit=None, format_kind="text"),
    )

    assert metric.source == "local"
    assert metric.source_badge == "local"
    assert metric.observation_date == "2026-01-02"
    assert metric.freshness_status == "fresh"


def test_generated_at_and_observation_date_characterization():
    payload_metric = dashboard_service._build_metric(
        "rate_pressure",
        (
            report(
                "market_snapshot",
                {
                    "generated_at": "report-generated",
                    "updated_at": "report-updated",
                    "dgs10": {
                        "value": 4.2,
                        "status": "ok",
                        "date": "2026-01-01",
                        "updated_at": "payload-updated",
                        "generated_at": "payload-generated",
                    },
                },
            ),
        ),
        _spec("dgs10"),
    )
    report_metric = dashboard_service._build_metric(
        "rate_pressure",
        (report("market_snapshot", {"updated_at": "report-updated", "dgs10": {"value": 4.2}}),),
        _spec("dgs10"),
    )
    none_metric = dashboard_service._build_metric(
        "rate_pressure",
        (report("market_snapshot", {"dgs10": {"value": 4.2}}),),
        _spec("dgs10"),
    )

    assert payload_metric.observation_date == "2026-01-01"
    assert payload_metric.generated_at == "payload-generated"
    assert report_metric.generated_at == "report-updated"
    assert none_metric.generated_at is None


def test_format_value_characterization():
    assert dashboard_service._format_value(1.234, "percent", "ok") == "1.23%"
    assert dashboard_service._format_value(1.234, "signed_percent", "ok") == "+1.23%"
    assert dashboard_service._format_value(1.23, "pp", "ok") == "+1.23pp"
    assert dashboard_service._format_value(1234, "number", "ok") == "1,234"
    assert dashboard_service._format_value(1234.5, "number", "ok") == "1,234.5"
    assert dashboard_service._format_value(True, "bool", "ok") == "true"
    assert dashboard_service._format_value(False, "bool", "ok") == "false"
    assert dashboard_service._format_value(None, "number", "missing") == "missing"
    assert dashboard_service._format_value(None, "number", "research_needed") == "research needed"
    assert dashboard_service._format_value(None, "number", "insufficient_history") == "insufficient history"
    assert dashboard_service._format_value(None, "number", "not_available") == "not available"
    assert dashboard_service._format_value(None, "number", "stale") == "stale"
    assert dashboard_service._format_value(None, "number", "ok") == "missing"


def test_key_metrics_for_module_special_routing_characterization(monkeypatch):
    calls = []

    def apply_historical(metrics, **kwargs):
        calls.append(("historical", kwargs))
        return metrics

    def apply_ppi(metrics, **kwargs):
        calls.append(("ppi", kwargs))
        return metrics

    def compact_fallback(reports):
        calls.append(("fallback", {}))
        return {"dgs10": {"value": 4.2}}

    monkeypatch.setattr(dashboard_service, "_apply_historical_derived_metrics", apply_historical)
    monkeypatch.setattr(dashboard_service, "_apply_ppi_final_demand_history", apply_ppi)
    monkeypatch.setattr(dashboard_service, "_compact_dgs_fallback_observations", compact_fallback)
    monkeypatch.setattr(dashboard_service, "_build_metric", lambda module_key, reports, spec: _metric(spec[0]))

    reports = (report("market_snapshot", {"generated_at": "2026-01-01"}),)

    dashboard_service._key_metrics_for_module("equity_trend", reports, market_history_db_path="db")
    dashboard_service._key_metrics_for_module("inflation_energy_pressure", reports, market_history_db_path="db")
    dashboard_service._key_metrics_for_module("breadth_concentration_proxy", reports, market_history_db_path="db")
    dashboard_service._key_metrics_for_module("market_stress_derived", reports, market_history_db_path="db")
    dashboard_service._key_metrics_for_module("rate_pressure", reports, market_history_db_path="db")
    dashboard_service._key_metrics_for_module("portfolio_deviation", reports, market_history_db_path="db")

    assert calls[0] == (
        "historical",
        {
            "module_key": "equity_trend",
            "metric_keys": dashboard_service.EQUITY_HISTORICAL_DERIVED_METRIC_KEYS,
            "hint_suffix": dashboard_service.EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX,
            "fallback_source": "local_market_history",
            "db_path": "db",
        },
    )
    assert [name for name, _ in calls[1:4]] == ["ppi", "historical", "historical"]
    assert calls[2][1]["metric_keys"] == dashboard_service.OIL_HISTORICAL_DERIVED_METRIC_KEYS
    assert calls[2][1]["required_dependency_source_badges"] == {"official"}
    assert calls[2][1]["replace_existing"] is True
    assert calls[3][1]["metric_keys"] == dashboard_service.PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS
    assert calls[3][1]["required_dependency_source_badges"] == {"official"}
    assert calls[3][1]["replace_existing"] is True
    assert calls[4][1]["metric_keys"] == dashboard_service.PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS
    assert calls[4][1]["required_dependency_source_badges"] == {"proxy"}
    assert calls[5][0] == "fallback"
    assert calls[6][1]["metric_keys"] == dashboard_service.MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS
    assert calls[6][1]["fallback_observations"] == {"dgs10": {"value": 4.2}}


def test_build_metric_derived_portfolio_find_order_characterization(monkeypatch):
    calls = []
    derived_metric = _metric("custom_metric", source_badge="derived")
    compact_metric = _metric("custom_metric", source_badge="local")

    monkeypatch.setattr(dashboard_service, "_derived_metric", lambda *args: calls.append("derived") or derived_metric)
    monkeypatch.setattr(dashboard_service, "_portfolio_compact_metric", lambda **kwargs: calls.append("compact") or compact_metric)
    monkeypatch.setattr(
        dashboard_service,
        "_find_metric",
        lambda *args, **kwargs: calls.append("find")
        or (1.0, _payload(1.0), report("market_snapshot", {"custom_metric": {"value": 1.0}})),
    )
    assert dashboard_service._build_metric("rate_pressure", (), _spec("custom_metric")) is derived_metric
    assert calls == ["derived"]

    calls.clear()
    monkeypatch.setattr(dashboard_service, "_derived_metric", lambda *args: calls.append("derived") or None)
    assert dashboard_service._build_metric("portfolio_deviation", (), _spec("custom_metric")) is compact_metric
    assert calls == ["derived", "compact"]

    calls.clear()
    monkeypatch.setattr(dashboard_service, "_portfolio_compact_metric", lambda **kwargs: calls.append("compact") or None)
    result = dashboard_service._build_metric(
        "rate_pressure",
        (report("market_snapshot", {"custom_metric": {"value": 1.0}}),),
        _spec("custom_metric", unit=None, format_kind="number"),
    )
    assert result.metric_key == "custom_metric"
    assert calls == ["derived", "compact", "find"]


def test_dependency_unusable_characterization():
    assert dashboard_service._dependency_unusable((1, {"status": "missing"}, report("x"))) is True
    assert dashboard_service._dependency_unusable((1, {"status": "ok", "freshness_status": "stale"}, report("x"))) is True
    assert dashboard_service._dependency_unusable((None, {"status": "ok", "freshness_status": "fresh"}, report("x"))) is True
    assert dashboard_service._dependency_unusable((1, {"status": "ok", "freshness_status": "fresh"}, report("x"))) is False


def test_historical_derived_metric_snapshot_characterization():
    original = _metric(
        "sp500_30d_return",
        source_badge="missing",
        status="insufficient_history",
        value=None,
        value_text="insufficient history",
        unit="percent",
        ai_context_allowed=False,
    )
    candidate = historical_derived_metrics.HistoricalDerivedMetric(
        metric_key="sp500_30d_return",
        value=0.1234,
        value_text="+12.34%",
        unit="percent",
        status="ok",
        source="local_market_history",
        source_badge="derived",
        observation_date="2026-03-02",
        generated_at="2026-03-03T00:00:00+00:00",
        freshness_status="historical",
        missing_reason=None,
        interpretation_hint="Derived from local market history.",
        ai_context_allowed=True,
        dependency_keys=["sp500"],
        window="30d",
        calculation="price_return",
        history_points_used=2,
        history_points_required=2,
        dependency_source_badges=["unofficial_fallback"],
        dependency_source_series=["^GSPC"],
    )

    metric = dashboard_service._historical_derived_metric(
        original,
        candidate,
        metric_keys={"sp500_30d_return"},
        hint_suffix=" Not an official market breadth measure.",
        fallback_source="local_market_history",
        required_dependency_source_badges={"unofficial_fallback"},
        replace_existing=False,
    )

    assert _metric_snapshot(metric) == {
        "metric_key": "sp500_30d_return",
        "display_name": "sp500_30d_return",
        "value": 12.34,
        "value_text": "+12.34%",
        "unit": "percent",
        "status": "ok",
        "source": "local_market_history",
        "source_badge": "derived",
        "source_series": "^GSPC",
        "observation_date": "2026-03-02",
        "generated_at": "2026-03-03T00:00:00+00:00",
        "freshness_status": "historical",
        "missing_reason": None,
        "interpretation_hint": (
            "Derived from local market history. Not an official market breadth measure."
        ),
        "ai_context_allowed": True,
    }


def test_portfolio_compact_metric_snapshot_characterization():
    portfolio_report = report(
        "portfolio_snapshot",
        {
            "generated_at": "2026-06-10T00:00:00+00:00",
            "holdings_updated_at": "2026-06-01",
            "weights_ex_cash": {
                "sp500": 0.54,
                "nasdaq100": 0.17,
                "short_bond": 0.19,
                "gold": 0.10,
            },
            "target_allocation": {
                "sp500": 0.50,
                "nasdaq100": 0.20,
                "short_bond": 0.20,
                "gold": 0.10,
            },
            "cash_reserve_value": 1234567,
            "holdings": [{"ticker": "RAW_FUND", "amount": 999999}],
        },
    )

    compact = dashboard_service._portfolio_deviation_compact(portfolio_report)
    metric = dashboard_service._portfolio_compact_metric(
        module_key="portfolio_deviation",
        reports=(portfolio_report,),
        metric_key="max_deviation_pp",
        display_name="Max deviation",
        unit="pp",
        format_kind="pp",
    )

    assert compact.max_deviation_asset == "sp500"
    assert compact.max_deviation_pp == 4.0
    assert compact.equity_total_deviation_pp == 1.0
    assert compact.cash_reserve_status == "cash_excluded_from_target_allocation"
    assert compact.stale_status == "fresh"
    assert _metric_snapshot(metric) == {
        "metric_key": "max_deviation_pp",
        "display_name": "Max deviation",
        "value": 4.0,
        "value_text": "+4.00pp",
        "unit": "pp",
        "status": "watch",
        "source": "local_portfolio_compact",
        "source_badge": "local",
        "source_series": None,
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-10T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": dashboard_service.PORTFOLIO_COMPACT_INTERPRETATION_HINT,
        "ai_context_allowed": True,
    }


def test_derived_status_metric_snapshot_characterization():
    reports = (
        report(
            "market_snapshot",
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "high_yield_spread": _payload(5.1, source_series="BAMLH0A0HYM2"),
                "investment_grade_spread": _payload(1.2, source_series="BAMLC0A0CM"),
                "vix": _payload(26.0, source_series="VIXCLS"),
            },
        ),
    )

    metric = dashboard_service._credit_stress_status_metric(reports)

    assert _metric_snapshot(metric) == {
        "metric_key": "credit_stress_status",
        "display_name": "Credit stress status",
        "value": "credit_pressure",
        "value_text": "credit_pressure",
        "unit": None,
        "status": "pressure",
        "source": "dashboard_compact",
        "source_badge": "derived",
        "source_series": None,
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": (
            "Derived from available credit spread evidence plus VIX. VIX alone is not "
            "sufficient to infer systemic credit stress or crisis."
        ),
        "ai_context_allowed": True,
    }


@pytest.mark.parametrize(
    ("case", "expected_allowed", "expected_badge"),
    [
        ("official_fresh_ok", True, "official"),
        ("missing", False, "official"),
        ("research_needed", False, "research_needed"),
        ("insufficient_history", False, "derived"),
        ("stale", False, "official"),
        ("search_derived", False, "search-derived"),
        ("proxy", False, "proxy"),
    ],
)
def test_ai_context_gate_through_build_metric_characterization(case, expected_allowed, expected_badge):
    payloads = {
        "official_fresh_ok": _payload(4.2, source_badge="official"),
        "missing": {"status": "missing", "value": None, "source_badge": "official"},
        "research_needed": {"status": "research_needed", "value": None, "source_badge": "research_needed"},
        "insufficient_history": {"status": "insufficient_history", "value": None, "source_badge": "derived"},
        "stale": _payload(4.2, source_badge="official", freshness_status="stale"),
        "search_derived": _payload(4.2, source_badge="search-derived"),
        "proxy": _payload(4.2, source_badge="proxy"),
    }
    metric = dashboard_service._build_metric(
        "rate_pressure",
        (report("market_snapshot", {"custom_metric": payloads[case]}),),
        _spec("custom_metric"),
    )

    assert metric.ai_context_allowed is expected_allowed
    assert metric.source_badge == expected_badge


def test_legacy_metric_builder_callable_surface_characterization():
    for name in (
        "_build_metric",
        "_key_metrics_for_module",
        "_missing_metric",
        "_metric_status",
        "_metric_freshness",
        "_metric_source",
        "_metric_source_badge",
        "_metric_observation_date",
        "_metric_generated_at",
        "_metric_quality_metadata",
        "_format_value",
        "_normalize_inflation_yoy_value",
        "_find_metric",
    ):
        assert callable(getattr(dashboard_service, name))


def report(name, data=None, *, exists=True, error_summary=None):
    return ReportState(
        name=name,
        path=Path(f"{name}.json"),
        exists=exists,
        data=data,
        error_summary=error_summary,
    )


def _payload(
    value,
    *,
    status="ok",
    source="FRED",
    source_badge="official",
    source_series="DGS10",
    observation_date="2026-01-01",
    generated_at="2026-01-01T00:00:00+00:00",
    freshness_status="fresh",
    unit=None,
):
    payload = {
        "value": value,
        "status": status,
        "source": source,
        "source_badge": source_badge,
        "source_series": source_series,
        "observation_date": observation_date,
        "generated_at": generated_at,
        "freshness_status": freshness_status,
    }
    if unit is not None:
        payload["unit"] = unit
    return payload


def _spec(
    metric_key,
    display_name=None,
    unit="percent",
    format_kind="percent",
    missing_status="missing",
):
    return (metric_key, display_name or metric_key, unit, format_kind, missing_status)


def _metric_snapshot(metric):
    fields = (
        "metric_key",
        "display_name",
        "value",
        "value_text",
        "unit",
        "status",
        "source",
        "source_badge",
        "source_series",
        "observation_date",
        "generated_at",
        "freshness_status",
        "missing_reason",
        "interpretation_hint",
        "ai_context_allowed",
    )
    payload = metric.model_dump()
    return {field: payload[field] for field in fields}


def _metric(
    metric_key,
    *,
    source_badge="official",
    status="ok",
    value=1.0,
    value_text="1.0",
    unit=None,
    ai_context_allowed=True,
):
    return DashboardMetric(
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=value_text,
        unit=unit,
        status=status,
        source="test",
        source_badge=source_badge,
        observation_date="2026-01-01",
        generated_at="2026-01-01T00:00:00+00:00",
        freshness_status="fresh",
        missing_reason=None,
        interpretation_hint=None,
        ai_context_allowed=ai_context_allowed,
    )
