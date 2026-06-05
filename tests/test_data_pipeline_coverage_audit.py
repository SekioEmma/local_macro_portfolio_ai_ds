import json
import socket

from app_backend.schemas.responses import DashboardEvidenceRow, DashboardMetric, DashboardModule
import audit_data_pipeline_coverage as audit


def test_audit_script_runs_against_fake_reports(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "dgs10": {
                "value": 4.5,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)

    assert result["coverage_summary"]["total_rows"] > 0
    assert result["module_coverage"]
    assert "recommendations" in result


def test_audit_detects_metadata_anomalies():
    rows = [
        _row(
            "rate_pressure",
            "dgs10",
            value=4.5,
            source_badge="missing",
            freshness_status="unknown",
            ai_context_allowed=True,
        )
    ]

    anomalies = audit._metadata_anomalies(rows)
    anomaly_types = {item["type"] for item in anomalies}

    assert "value_with_missing_source_badge" in anomaly_types
    assert "value_with_unknown_freshness" in anomaly_types
    assert "ai_allowed_with_missing_source_badge" in anomaly_types
    assert "ai_allowed_with_bad_freshness" in anomaly_types


def test_audit_detects_derived_dependency_anomalies():
    rows = [
        _row("rate_pressure", "dgs10", value=None, status="missing"),
        _row("rate_pressure", "dgs30", value=None, status="missing"),
        _row(
            "rate_pressure",
            "dgs30_distance_to_5pct",
            value=0.2,
            status="ok",
            source_badge="derived",
        ),
        _row("equity_trend", "sp500_30d_return", value=None, status="insufficient_history"),
        _row(
            "equity_trend",
            "nasdaq100_30d_return",
            value=3.1,
            status="ok",
            source_badge="unofficial_fallback",
        ),
        _row(
            "equity_trend",
            "nasdaq_vs_sp500_30d",
            value=1.1,
            status="ok",
            source_badge="derived",
        ),
    ]
    modules = {
        "rate_pressure": _module("rate_pressure", "ok"),
        "equity_trend": _module("equity_trend", "ok"),
    }

    anomalies = audit._dependency_anomalies(modules, rows)
    anomaly_types = {item["type"] for item in anomalies}

    assert "dgs30_distance_ok_while_dgs30_missing" in anomaly_types
    assert "nasdaq_vs_sp500_ok_while_dependency_missing" in anomaly_types
    assert "module_ok_while_core_metrics_mostly_missing" in anomaly_types


def _row(
    module,
    metric_key,
    *,
    value,
    status="ok",
    source_badge="official",
    freshness_status="fresh",
    ai_context_allowed=False,
):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value) if value is not None else status,
        unit=None,
        status=status,
        source="FRED" if source_badge not in {"missing", "derived"} else None,
        source_badge=source_badge,
        observation_date="2026-01-01" if value is not None else None,
        generated_at=None,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=None,
        ai_context_allowed=ai_context_allowed,
    )


def _module(key, status):
    return DashboardModule(
        key=key,
        status=status,
        label=key,
        summary=None,
        source_badge="cached_report",
        updated_at=None,
        next_action=None,
        error_summary=None,
        key_metrics=[
            DashboardMetric(
                metric_key="placeholder",
                display_name="placeholder",
                value=None,
                value_text="missing",
                unit=None,
                status="missing",
                source=None,
                source_badge="missing",
                observation_date=None,
                generated_at=None,
                freshness_status="missing",
                missing_reason="missing",
                interpretation_hint=None,
                ai_context_allowed=False,
            )
        ],
    )


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in audit tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
