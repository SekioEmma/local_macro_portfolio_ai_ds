from pathlib import Path

from audit_sections import module_audits
from data_quality import portfolio_exposure_overlay as overlay
from modeling.metric_lookup import MetricLookup
from modeling.model_registry import ModelRegistry

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_stage8_public_keys_match_model_registry_metric_lookup_and_frontend_registry():
    registry = ModelRegistry()
    lookup = MetricLookup()
    public_keys = set(registry.public_output_keys("portfolio_exposure_overlay"))
    frontend_metric_registry = (_REPO_ROOT / "app_frontend/src/utils/metricRegistry.ts").read_text(
        encoding="utf-8"
    )
    frontend_module_registry = (_REPO_ROOT / "app_frontend/src/utils/moduleRegistry.ts").read_text(
        encoding="utf-8"
    )

    assert public_keys == set(lookup.public_output_keys("portfolio_exposure_overlay"))
    assert public_keys == set(overlay.PUBLIC_OUTPUT_KEYS)
    assert public_keys == module_audits.PORTFOLIO_EXPOSURE_OVERLAY_METRIC_KEYS
    for metric_key in public_keys:
        assert lookup.require(metric_key).module == "portfolio_exposure_overlay"
        assert f"{metric_key}:" in frontend_metric_registry
    assert 'portfolio_exposure_overlay: "Portfolio exposure overlay"' in frontend_module_registry
    assert "privacy-preserving explanatory layer" in frontend_module_registry


def test_stage8_audit_count_matches_registry_and_has_no_missing_public_keys():
    rows = [
        _evidence_row(payload)
        for payload in overlay.build_portfolio_exposure_overlay_rows(
            [
                _base_row("max_deviation_asset", "equity", module="portfolio_deviation"),
                _base_row("max_deviation_pp", 2.5, module="portfolio_deviation"),
                _base_row("financial_stress_status", "watch", module="financial_stress_composite"),
            ]
        )
    ]

    result = module_audits._portfolio_exposure_overlay_audit(rows)

    assert result["configured_public_output_count"] == len(
        ModelRegistry().public_output_keys("portfolio_exposure_overlay")
    )
    assert result["missing_public_output_keys"] == []
    assert result["portfolio_overlay_cannot_trigger_macro_regime"] is True
    assert result["portfolio_overlay_cannot_change_scenario_severity"] is True
    assert result["portfolio_overlay_downstream_only"] is True
    assert all(row.source_badge == "derived" for row in rows)
    assert all(row.trigger_eligibility == "overlay_only" for row in rows)


def _base_row(metric_key, value, *, module):
    return {
        "module": module,
        "metric_key": metric_key,
        "value": value,
        "value_text": str(value),
        "status": "ok",
        "source_badge": "local" if module == "portfolio_deviation" else "derived",
        "freshness_status": "fresh",
        "ai_context_allowed": True,
        "observation_date": "2026-06-01",
    }


def _evidence_row(payload):
    from app_backend.schemas.responses import DashboardEvidenceRow

    return DashboardEvidenceRow(
        row_id=f"portfolio_exposure_overlay:{payload['metric_key']}",
        module="portfolio_exposure_overlay",
        **payload,
    )
