from __future__ import annotations

import json
import socket

from app_backend.services import ai_context_service
from app_backend.services import dashboard_context
from app_backend.services import dashboard_filters
from app_backend.services import dashboard_service


def test_dashboard_pipeline_context_import_is_reexported():
    assert dashboard_service.DashboardPipelineContext is dashboard_context.DashboardPipelineContext


def test_dashboard_pipeline_context_starts_empty():
    context = dashboard_service.DashboardPipelineContext()

    assert context.summary is None
    assert context.evidence_table is None


def test_evidence_table_reuses_context_summary(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    summary = dashboard_service.build_dashboard_summary(reports_dir=tmp_path)
    context = dashboard_service.DashboardPipelineContext(summary=summary)
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_summary",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("summary should be reused")),
    )

    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
        context=context,
    )

    assert evidence.generated_at == summary.generated_at
    assert evidence.row_count > 0
    assert context.evidence_table is evidence


def test_evidence_table_builds_summary_when_context_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    original = dashboard_service.build_dashboard_summary
    calls = {"count": 0}

    def wrapped(**kwargs):
        calls["count"] += 1
        return original(**kwargs)

    monkeypatch.setattr(dashboard_service, "build_dashboard_summary", wrapped)
    context = dashboard_service.DashboardPipelineContext()

    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
        context=context,
    )

    assert calls["count"] == 1
    assert context.summary is not None
    assert context.evidence_table is evidence


def test_ai_manifest_reuses_context_evidence(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
    )
    context = dashboard_service.DashboardPipelineContext(evidence_table=evidence)
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("evidence should be reused")),
    )

    manifest = ai_context_service.build_ai_context_manifest(context=context)

    assert manifest.generated_at == evidence.generated_at
    assert manifest.source_summary["total_evidence_rows"] == len(evidence.rows)


def test_ai_manifest_builds_evidence_when_context_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    original = dashboard_service.build_dashboard_evidence_table
    calls = {"count": 0}

    def wrapped(**kwargs):
        calls["count"] += 1
        return original(**kwargs)

    monkeypatch.setattr(dashboard_service, "build_dashboard_evidence_table", wrapped)
    context = dashboard_service.DashboardPipelineContext()

    manifest = ai_context_service.build_ai_context_manifest(context=context)

    assert calls["count"] == 1
    assert context.evidence_table is not None
    assert manifest.source_summary["total_evidence_rows"] == len(context.evidence_table.rows)


def test_shared_context_outputs_equal_legacy_outputs(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    legacy_summary = dashboard_service.build_dashboard_summary(reports_dir=tmp_path)
    legacy_evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
    )
    legacy_manifest = ai_context_service.build_ai_context_manifest()
    context = dashboard_service.DashboardPipelineContext()

    shared_summary = dashboard_service.build_dashboard_summary(
        reports_dir=tmp_path,
        context=context,
    )
    shared_evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
        context=context,
    )
    shared_manifest = ai_context_service.build_ai_context_manifest(context=context)

    assert _stable(legacy_summary) == _stable(shared_summary)
    assert _stable(legacy_evidence) == _stable(shared_evidence)
    assert _stable(legacy_manifest.included_facts) == _stable(shared_manifest.included_facts)
    assert _stable(legacy_manifest.excluded_facts) == _stable(shared_manifest.excluded_facts)
    assert _stable(legacy_manifest.included_model_outputs) == _stable(shared_manifest.included_model_outputs)
    assert _stable(legacy_manifest.excluded_model_outputs) == _stable(shared_manifest.excluded_model_outputs)
    assert legacy_manifest.privacy_policy == shared_manifest.privacy_policy


def test_write_last_good_false_is_respected_with_context(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    context = dashboard_service.DashboardPipelineContext()
    monkeypatch.setattr(
        dashboard_service,
        "_save_last_good_candidates",
        lambda rows: (_ for _ in ()).throw(AssertionError("last_good write should be skipped")),
    )

    dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
        context=context,
    )


def test_evidence_filters_still_work_with_context_summary(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    context = dashboard_service.DashboardPipelineContext(
        summary=dashboard_service.build_dashboard_summary(reports_dir=tmp_path)
    )

    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        module="rate_pressure",
        status="ok",
        source_badge="official",
        ai_context_allowed=True,
        write_last_good=False,
        context=context,
    )

    assert evidence.rows
    assert all(row.module == "rate_pressure" for row in evidence.rows)
    assert all(row.status == "ok" for row in evidence.rows)
    assert all(row.source_badge == "official" for row in evidence.rows)
    assert all(row.ai_context_allowed is True for row in evidence.rows)
    assert context.evidence_table is None


def test_extracted_evidence_filters_match_service_filtering(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    filters = {
        "module": "rate_pressure",
        "status": "ok",
        "source_badge": "official",
        "ai_context_allowed": True,
    }
    unfiltered = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
    )

    expected_rows = dashboard_filters.apply_evidence_filters(
        unfiltered.rows,
        **filters,
    )
    filtered = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
        **filters,
    )

    assert filtered.row_count == len(expected_rows)
    assert _stable(filtered.rows) == _stable(expected_rows)


def test_unfiltered_context_row_order_matches_legacy(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)

    legacy = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
    )
    context = dashboard_service.DashboardPipelineContext()
    shared = dashboard_service.build_dashboard_evidence_table(
        reports_dir=tmp_path,
        write_last_good=False,
        context=context,
    )

    assert [row.row_id for row in shared.rows] == [row.row_id for row in legacy.rows]
    assert shared.row_count == legacy.row_count


def test_write_last_good_true_does_not_reuse_context_evidence(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    _write_reports(first_dir, dgs10=4.1)
    _write_reports(second_dir, dgs10=5.2)
    first = dashboard_service.build_dashboard_evidence_table(
        reports_dir=first_dir,
        write_last_good=False,
    )
    context = dashboard_service.DashboardPipelineContext(evidence_table=first)

    second = dashboard_service.build_dashboard_evidence_table(
        reports_dir=second_dir,
        write_last_good=True,
        context=context,
    )

    assert second is not first
    assert _row(second, "rate_pressure", "dgs10").value == 5.2
    assert context.evidence_table is first


def test_no_process_level_stale_cache_between_contexts(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    _write_reports(first_dir, dgs10=4.1)
    _write_reports(second_dir, dgs10=5.2)

    first = dashboard_service.build_dashboard_evidence_table(
        reports_dir=first_dir,
        write_last_good=False,
        context=dashboard_service.DashboardPipelineContext(),
    )
    second = dashboard_service.build_dashboard_evidence_table(
        reports_dir=second_dir,
        write_last_good=False,
        context=dashboard_service.DashboardPipelineContext(),
    )

    assert _row(first, "rate_pressure", "dgs10").value != _row(second, "rate_pressure", "dgs10").value


def _row(evidence, module, metric_key):
    for row in evidence.rows:
        if row.module == module and row.metric_key == metric_key:
            return row
    raise AssertionError(f"missing {module}:{metric_key}")


def _stable(value):
    if hasattr(value, "model_dump"):
        return _stable(value.model_dump())
    if isinstance(value, dict):
        return {
            key: _stable(item)
            for key, item in value.items()
            if key not in {"generated_at", "created_at", "updated_at"}
        }
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _write_reports(tmp_path, *, dgs10=4.52):
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
                "dgs10": metric(dgs10),
                "dgs30": metric(4.83),
                "dfii10": metric(2.1),
                "t10yie": metric(2.35),
                "real_yield_pressure_status": metric("pressure"),
                "core_cpi_yoy": metric(3.1),
                "core_pce_yoy": metric(2.8),
                "ppiaco_yoy": metric(1.7),
                "unemployment_rate": metric(4.0),
                "initial_jobless_claims": metric(230000),
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
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in M3 tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
