from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app_backend.services import dashboard_service


def write_dashboard_reports(
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


def install_default_reports(monkeypatch, reports_dir: Path, *, dgs10: float = 4.52) -> None:
    write_dashboard_reports(reports_dir, dgs10=dgs10)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", reports_dir)


@pytest.fixture
def block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
