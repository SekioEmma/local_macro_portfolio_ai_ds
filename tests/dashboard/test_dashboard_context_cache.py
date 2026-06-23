from __future__ import annotations

import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.schemas.responses import (
    DashboardEvidenceTableResponse,
    DashboardSummaryResponse,
)
from app_backend.services import dashboard_service
from app_backend.services.dashboard_context_cache import (
    CachedDashboardContext,
    SharedDashboardContextCache,
)


def setup_function() -> None:
    dashboard_service._SHARED_DASHBOARD_CONTEXT_CACHE.clear()


def teardown_function() -> None:
    dashboard_service._SHARED_DASHBOARD_CONTEXT_CACHE.clear()


def test_cache_hit_returns_identical_default_summary_and_evidence(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path)
    calls = _count_pipeline_builds(monkeypatch)

    first = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    second = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    summary = dashboard_service.build_dashboard_summary()

    assert calls["count"] == 1
    assert second.row_count == first.row_count
    assert second.modules == first.modules
    assert _row_signature(second) == _row_signature(first)
    assert set(summary.modules) <= set(second.modules)
    assert "cache_key" not in second.model_dump()


def test_concurrent_summary_builds_share_one_locked_build(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path)
    original = dashboard_service._load_dashboard_reports
    count_lock = Lock()
    calls = {"count": 0}

    def wrapped(reports_dir):
        with count_lock:
            calls["count"] += 1
        time.sleep(0.05)
        return original(reports_dir)

    monkeypatch.setattr(dashboard_service, "_load_dashboard_reports", wrapped)

    with ThreadPoolExecutor(max_workers=4) as executor:
        summaries = list(executor.map(lambda _: dashboard_service.build_dashboard_summary(), range(4)))

    assert calls["count"] == 1
    assert all(summary == summaries[0] for summary in summaries[1:])


def test_cache_invalidates_on_report_file_stat_change(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path, dgs10=4.1)
    calls = _count_pipeline_builds(monkeypatch)

    first = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    _write_reports(tmp_path, dgs10=5.25, generated_at="2026-01-01T00:00:00+00:00Z-extra")
    os.utime(tmp_path / "market_snapshot.json", None)
    second = dashboard_service.build_dashboard_evidence_table(write_last_good=False)

    assert calls["count"] == 2
    assert _row(first, "rate_pressure", "dgs10").value == 4.1
    assert _row(second, "rate_pressure", "dgs10").value == 5.25


def test_cache_invalidates_on_market_history_db_stat_change(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_reports(reports_dir)
    db_path = tmp_path / "market_history.sqlite3"
    db_path.write_text("db", encoding="utf-8")
    cache = SharedDashboardContextCache()
    first_key = dashboard_service._build_dashboard_cache_key_for_request(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    cache.set(
        CachedDashboardContext(
            key_digest=first_key.digest,
            summary=_dummy_summary(),
            unfiltered_evidence_table=_dummy_evidence_table(),
        )
    )

    db_path.write_text("db-changed", encoding="utf-8")
    os.utime(db_path, None)
    second_key = dashboard_service._build_dashboard_cache_key_for_request(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )

    assert second_key.digest != first_key.digest
    assert cache.get(second_key.digest) is None


def test_write_last_good_uses_cache_but_still_saves(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path)
    calls = _count_pipeline_builds(monkeypatch)
    saves = {"count": 0}
    monkeypatch.setattr(dashboard_service, "_last_good_write_allowed", lambda reports_dir: True)
    monkeypatch.setattr(
        dashboard_service,
        "_save_last_good_candidates",
        lambda rows: saves.__setitem__("count", saves["count"] + 1),
    )

    dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    dashboard_service.build_dashboard_evidence_table(write_last_good=True)
    dashboard_service.build_dashboard_evidence_table(write_last_good=True)

    assert calls["count"] == 1
    assert saves["count"] == 2


def test_custom_path_bypasses_and_does_not_poison_default_cache(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    default_dir = tmp_path / "default"
    custom_dir = tmp_path / "custom"
    default_dir.mkdir()
    custom_dir.mkdir()
    _write_reports(default_dir, dgs10=4.1)
    _write_reports(custom_dir, dgs10=5.2)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", default_dir)
    calls = _count_pipeline_builds(monkeypatch)

    default_first = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    custom = dashboard_service.build_dashboard_evidence_table(
        reports_dir=custom_dir,
        write_last_good=False,
    )
    default_second = dashboard_service.build_dashboard_evidence_table(write_last_good=False)

    assert calls["count"] == 2
    assert _row(default_first, "rate_pressure", "dgs10").value == 4.1
    assert _row(custom, "rate_pressure", "dgs10").value == 5.2
    assert _row(default_second, "rate_pressure", "dgs10").value == 4.1


def test_preloaded_context_summary_bypasses_and_does_not_poison_cache(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    default_dir = tmp_path / "default"
    context_dir = tmp_path / "context"
    default_dir.mkdir()
    context_dir.mkdir()
    _write_reports(default_dir, dgs10=4.1)
    _write_reports(context_dir, dgs10=5.2)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", default_dir)
    calls = _count_pipeline_builds(monkeypatch)

    default_first = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    summary = dashboard_service.build_dashboard_summary(reports_dir=context_dir)
    context = dashboard_service.DashboardPipelineContext(summary=summary)
    context_evidence = dashboard_service.build_dashboard_evidence_table(
        write_last_good=False,
        context=context,
    )
    default_second = dashboard_service.build_dashboard_evidence_table(write_last_good=False)

    assert calls["count"] == 2
    assert _row(default_first, "rate_pressure", "dgs10").value == 4.1
    assert _row(context_evidence, "rate_pressure", "dgs10").value == 5.2
    assert _row(default_second, "rate_pressure", "dgs10").value == 4.1


def test_filtered_calls_do_not_poison_unfiltered_cache(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path)
    calls = _count_pipeline_builds(monkeypatch)

    filtered = dashboard_service.build_dashboard_evidence_table(
        module="rate_pressure",
        write_last_good=False,
    )
    unfiltered = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    filtered_again = dashboard_service.build_dashboard_evidence_table(
        module="rate_pressure",
        write_last_good=False,
    )

    assert calls["count"] == 1
    assert 0 < filtered.row_count <= unfiltered.row_count
    assert filtered_again.row_count == filtered.row_count
    assert unfiltered.modules == sorted({row.module for row in unfiltered.rows})
    assert all(row.module == "rate_pressure" for row in filtered.rows)


def test_cached_responses_are_defensive_copies(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path)
    dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    cached = dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    original_module = cached.rows[0].module

    cached.rows[0].module = "mutated_module"
    cached.rows.append(cached.rows[0])
    cached.next_actions.append("mutated_action")
    clean = dashboard_service.build_dashboard_evidence_table(write_last_good=False)

    assert clean.rows[0].module == original_module
    assert clean.row_count == len(clean.rows)
    assert "mutated_action" not in clean.next_actions


def test_no_private_payload_or_cache_diagnostics_in_route_responses(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _install_default_reports(monkeypatch, tmp_path)
    client = TestClient(app)

    dashboard_service.build_dashboard_evidence_table(write_last_good=False)
    for response in (
        client.get("/api/dashboard/summary"),
        client.get("/api/dashboard/evidence-table"),
        client.get("/api/context/manifest"),
    ):
        assert response.status_code == 200
        text = response.text
        for token in (
            "cache_key",
            "cache_payload",
            "cache_hit",
            "cache_miss",
            "SECRET_HOLDING_LINE_ITEM",
            "PRIVATE_ACCOUNT_VALUE",
            "RAW_PROMPT_TEXT",
            "PROVIDER_SECRET",
        ):
            assert token not in text


def test_dashboard_context_cache_helper_has_no_forbidden_product_surfaces():
    text = Path("src/app_backend/services/dashboard_context_cache.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/external",
        "DeepSeek",
        "Tavily",
        "external_llm.yaml",
        ".env",
        "scenario_probability",
        "forecast_path",
        "expected_return",
        "target_price",
        "portfolio_action",
        "trade_signal",
        "target_allocation",
        "buy",
        "sell",
        "hedge",
        "rebalance",
    ):
        assert token not in text


def _install_default_reports(monkeypatch, reports_dir: Path, *, dgs10: float = 4.52) -> None:
    _write_reports(reports_dir, dgs10=dgs10)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", reports_dir)


def _count_pipeline_builds(monkeypatch):
    original = dashboard_service.build_dashboard_model_rows
    calls = {"count": 0}

    def wrapped(**kwargs):
        calls["count"] += 1
        return original(**kwargs)

    monkeypatch.setattr(dashboard_service, "build_dashboard_model_rows", wrapped)
    return calls


def _row_signature(evidence):
    return [
        (row.module, row.metric_key, row.status, row.source_badge, row.ai_context_allowed)
        for row in evidence.rows
    ]


def _row(evidence, module, metric_key):
    for row in evidence.rows:
        if row.module == module and row.metric_key == metric_key:
            return row
    raise AssertionError(f"missing {module}:{metric_key}")


def _dummy_summary() -> DashboardSummaryResponse:
    return DashboardSummaryResponse(
        generated_at="2026-01-01T00:00:00+00:00",
        overall_status="ok",
        overall_risk_level="watch",
        modules={},
        provider_health={},
        missing_data=[],
        data_freshness={},
        next_actions=[],
    )


def _dummy_evidence_table() -> DashboardEvidenceTableResponse:
    return DashboardEvidenceTableResponse(
        generated_at="2026-01-01T00:00:00+00:00",
        overall_status="ok",
        row_count=0,
        modules=[],
        rows=[],
        filters={"available": {}, "applied": {}},
        next_actions=[],
    )


def _write_reports(
    tmp_path: Path,
    *,
    dgs10: float = 4.52,
    generated_at: str = "2026-01-01T00:00:00+00:00",
) -> None:
    def metric(value, source="FRED", badge="official"):
        return {
            "value": value,
            "status": "ok",
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
                "wti_30d_change": metric(-4.2, source="EIA"),
                "brent_30d_change": metric(-3.8, source="EIA"),
                "sp500_30d_return": metric(2.2, source="yfinance"),
                "sp500_60d_return": metric(5.1, source="yfinance"),
                "nasdaq100_30d_return": metric(3.3, source="yfinance"),
                "nasdaq100_60d_return": metric(6.4, source="yfinance"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "market_temperature.json").write_text(
        json.dumps({"generated_at": generated_at, "status": "watch"}),
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
    (tmp_path / "provider_health_check.json").write_text(
        json.dumps({"generated_at": generated_at, "overall_status": "ok"}),
        encoding="utf-8",
    )


def _block_network(monkeypatch) -> None:
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in cache tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
