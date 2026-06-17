from pathlib import Path

import benchmark_dashboard_pipeline as bench


def test_pipeline_benchmark_exposes_reuse_flags(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_minimal_report(tmp_path)

    result = bench.run_benchmark(
        reports_dir=tmp_path,
        market_history_db_path=tmp_path / "absent.sqlite3",
    )

    assert result["pipeline_context_available"] is True
    assert result["summary_reused_by_evidence"] is True
    assert result["evidence_reused_by_manifest"] is True
    assert result["estimated_rebuilds_avoided"] == 2
    assert (
        result["shared_context_calls"]["summary_reused_by_evidence"]
        == result["summary_reused_by_evidence"]
    )
    assert (
        result["shared_context_calls"]["evidence_reused_by_manifest"]
        == result["evidence_reused_by_manifest"]
    )


def test_stage8_public_key_constant_uses_semantic_name():
    metric_lookup = Path("src/modeling/metric_lookup.py").read_text(encoding="utf-8")
    model_registry = Path("src/modeling/model_registry.py").read_text(encoding="utf-8")

    assert "PORTFOLIO_EXPOSURE_OVERLAY_PUBLIC_KEYS" in metric_lookup
    assert "PORTFOLIO_EXPOSURE_OVERLAY_PUBLIC_KEYS" in model_registry
    assert "D20_PUBLIC_OUTPUT_KEYS" not in metric_lookup
    assert "D20_PUBLIC_OUTPUT_KEYS" not in model_registry


def _write_minimal_report(tmp_path):
    (tmp_path / "market_snapshot.json").write_text(
        '{"generated_at":"2026-01-01T00:00:00+00:00","status":"ok"}',
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    import socket

    def _raise(*args, **kwargs):
        raise AssertionError("Network access is not allowed in stabilization tests.")

    monkeypatch.setattr(socket, "create_connection", _raise)
