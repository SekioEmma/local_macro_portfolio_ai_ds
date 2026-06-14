from __future__ import annotations

from types import SimpleNamespace

from app_backend.schemas.responses import DashboardEvidenceRow
from app_backend.services import ai_context_service
from app_backend.services import dashboard_service
from data_quality import financial_stress_composite
from data_quality import liquidity_funding_stress as d14
from data_quality import market_history_store
from data_quality import pullback_systemic_checklist
import ingest_liquidity_funding_history


def test_dry_run_does_not_fetch_or_write_db(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"

    def fetcher(*args, **kwargs):
        raise AssertionError("dry-run must not fetch")

    summary = ingest_liquidity_funding_history.build_ingest_summary(
        db_path=db_path,
        dry_run=True,
        live=False,
        fetcher=fetcher,
    )

    assert summary["fetched_series_count"] == 0
    assert summary["inserted_count"] == 0
    assert summary["updated_count"] == 0
    assert not db_path.exists()


def test_live_without_write_fetches_but_does_not_write_db(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"

    summary = ingest_liquidity_funding_history.build_ingest_summary(
        db_path=db_path,
        dry_run=True,
        live=True,
        limit=2,
        fetcher=_fake_fetcher,
    )

    assert summary["fetched_series_count"] > 0
    assert summary["normalized_observations"] > 0
    assert summary["inserted_count"] == 0
    assert summary["updated_count"] == 0
    assert not db_path.exists()


def test_research_needed_rows_are_emitted_for_missing_mappings(tmp_path):
    rows = _by_key(d14.build_liquidity_funding_rows(db_path=tmp_path / "empty.sqlite3"))

    assert rows["ofr_fsi"]["status"] == "research_needed"
    assert rows["ofr_fsi"]["source_badge"] == "research_needed"
    assert rows["ofr_fsi"]["missing_reason"] == "source_mapping_required"
    assert rows["ofr_fsi"]["ai_context_allowed"] is False


def test_official_rows_preserve_source_badge_series_and_date(tmp_path):
    db_path = _db_with_observations(tmp_path, sofr=4.32)

    row = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))["sofr"]

    assert row["status"] == "ok"
    assert row["source"] == "FRED"
    assert row["source_badge"] == "official"
    assert row["source_series"] == "SOFR"
    assert row["observation_date"] == "2026-06-01"


def test_derived_spreads_preserve_input_evidence_and_alignment(tmp_path):
    db_path = _db_with_observations(tmp_path, sofr=4.35, effr=4.30)

    spread = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))["sofr_effr_spread"]

    assert spread["value"] == 0.05
    assert spread["source_badge"] == "derived"
    assert {item["metric_key"] for item in spread["input_evidence"]} == {"sofr", "effr"}
    assert spread["component_contributions"]["alignment"] == "as_of_latest_available_observations"
    assert spread["component_contributions"]["forward_fill_used"] is False


def test_cp_spread_supports_pressure_but_not_systemic_crisis_alone(tmp_path):
    db_path = _db_with_observations(
        tmp_path,
        sofr=4.0,
        effr=4.0,
        iorb=4.0,
        cp=5.2,
        stl=-0.2,
        nfci=-0.1,
        anfci=-0.1,
    )
    rows = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))

    assert rows["short_term_funding_pressure_status"]["status"] == "pressure"
    assert rows["liquidity_funding_stress_status"]["value"] == "watch"
    assert rows["liquidity_funding_stress_status"]["value"] != "stress"


def test_on_rrp_alone_cannot_trigger_pressure_or_stress(tmp_path):
    db_path = _db_with_observations(tmp_path, on_rrp=2500.0)
    rows = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))

    assert rows["policy_plumbing_status"]["status"] == "insufficient_evidence"
    assert rows["liquidity_funding_stress_status"]["status"] == "insufficient_evidence"


def test_official_fsi_alone_cannot_replace_d10_or_trigger_crisis(tmp_path):
    db_path = _db_with_observations(tmp_path, stl=2.5, nfci=1.2, anfci=1.1)
    rows = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))

    assert rows["official_stress_reference_status"]["status"] == "stress"
    assert rows["liquidity_funding_stress_status"]["value"] == "watch"
    assert "do not replace" in rows["official_stress_reference_status"]["interpretation_hint"]


def test_mixed_frequencies_require_as_of_alignment_metadata(tmp_path):
    db_path = _db_with_observations(tmp_path, sofr=4.35, effr=4.30, effr_date="2026-05-31")
    spread = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))["sofr_effr_spread"]

    assert spread["component_contributions"]["mixed_frequency"] is True
    assert spread["component_contributions"]["forward_fill_used"] is False
    assert spread["component_contributions"]["input_observation_dates"] == {
        "sofr": "2026-06-01",
        "effr": "2026-05-31",
    }


def test_missing_cp_and_reference_indices_is_insufficient_evidence(tmp_path):
    db_path = _db_with_observations(tmp_path, sofr=4.0, effr=4.0, iorb=4.0)
    status = _by_key(d14.build_liquidity_funding_rows(db_path=db_path))[
        "liquidity_funding_stress_status"
    ]

    assert status["status"] == "insufficient_evidence"
    assert "short_term_funding_pressure_status" in status["missing_inputs"]
    assert "official_stress_reference_status" in status["missing_inputs"]


def test_ai_context_includes_eligible_d14_and_excludes_ineligible(monkeypatch):
    rows = [
        _evidence_row("sofr", 4.3, source_badge="official"),
        _evidence_row(
            "ofr_fsi",
            None,
            status="research_needed",
            source_badge="research_needed",
            ai_context_allowed=False,
        ),
        _evidence_row(
            "liquidity_funding_stress_status",
            "ok",
            source_badge="derived",
            interpretation_hint="Derived from local market history.",
        ),
    ]
    monkeypatch.setattr(
        dashboard_service,
        "build_dashboard_evidence_table",
        lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
    )

    manifest = ai_context_service.build_ai_context_manifest()
    included = {row["metric_key"]: row for row in manifest.included_facts}
    excluded = {row["metric_key"]: row for row in manifest.excluded_facts}

    assert "sofr" in included
    assert included["sofr"]["interpretation_boundary"] == d14.BOUNDARY
    assert "liquidity_funding_stress_status" in included
    assert excluded["ofr_fsi"]["excluded_reason"] in {
        "source_badge_research_needed",
        "status_research_needed",
    }


def test_d14_does_not_change_d10_or_d11_classification():
    base_rows = [
        _simple_row("credit_stress", "high_yield_spread", 3.0),
        _simple_row("credit_stress", "investment_grade_spread", 1.0),
        _simple_row("credit_stress", "vix", 16.0),
        _simple_row("rate_pressure", "dgs30", 4.2),
        _simple_row("real_yield_pressure", "dfii10", 1.8),
        _simple_row("market_stress_derived", "sp500_drawdown_3m", -0.03, badge="derived"),
        _simple_row("labor_macro", "labor_deterioration_status", "ok", badge="derived"),
    ]
    d14_rows = [
        _simple_row("liquidity_funding_stress", "liquidity_funding_stress_status", "stress", badge="derived")
    ]

    stress_before = _by_key(financial_stress_composite.build_financial_stress_rows(base_rows))
    stress_after = _by_key(financial_stress_composite.build_financial_stress_rows(base_rows + d14_rows))
    pullback_before = _by_key(
        pullback_systemic_checklist.build_pullback_checklist_rows(
            base_rows + list(stress_before.values())
        )
    )
    pullback_after = _by_key(
        pullback_systemic_checklist.build_pullback_checklist_rows(
            base_rows + d14_rows + list(stress_after.values())
        )
    )

    assert stress_after["financial_stress_status"]["value"] == stress_before["financial_stress_status"]["value"]
    assert pullback_after["pullback_classification"]["value"] == pullback_before["pullback_classification"]["value"]


def test_no_probability_trading_or_private_payload_leakage(tmp_path):
    db_path = _db_with_observations(tmp_path, sofr=4.35, effr=4.30, cp=4.8)
    body = str(d14.build_liquidity_funding_rows(db_path=db_path)).lower()

    assert "event odds" in body
    assert "business-cycle call" in body
    assert "allocation directive" in body
    assert "raw_provider" not in body
    assert "raw_holdings" not in body
    assert "sk-" not in body


def _fake_fetcher(series_id, limit):
    return {
        "status": "ok",
        "series_id": series_id,
        "timestamp": "2026-06-01T00:00:00+00:00",
        "data": [
            {"date": "2026-05-31", "value": "4.20"},
            {"date": "2026-06-01", "value": "4.30"},
        ][:limit],
    }


def _db_with_observations(
    tmp_path,
    *,
    sofr=None,
    effr=None,
    iorb=None,
    on_rrp=None,
    cp=None,
    stl=None,
    nfci=None,
    anfci=None,
    effr_date="2026-06-01",
):
    db_path = tmp_path / "market_history.sqlite3"
    values = {
        "sofr": (sofr, "SOFR", "official", "percent", "2026-06-01"),
        "effr": (effr, "EFFR", "official", "percent", effr_date),
        "iorb": (iorb, "IORB", "official", "percent", "2026-06-01"),
        "on_rrp": (on_rrp, "RRPONTSYD", "official", "billions_usd", "2026-06-01"),
        "commercial_paper_rate": (cp, "DCPF3M", "official_fallback", "percent", "2026-06-01"),
        "stl_fsi": (stl, "STLFSI4", "official_fallback", "index", "2026-05-29"),
        "nfci": (nfci, "NFCI", "official_fallback", "index", "2026-05-29"),
        "anfci": (anfci, "ANFCI", "official_fallback", "index", "2026-05-29"),
    }
    for metric_key, (value, series, badge, unit, observation_date) in values.items():
        if value is None:
            continue
        market_history_store.upsert_market_observation(
            {
                "metric_key": metric_key,
                "observation_date": observation_date,
                "value": value,
                "value_text": str(value),
                "unit": unit,
                "status": "ok",
                "source": "FRED",
                "source_badge": badge,
                "provider": "FRED",
                "source_series": series,
                "generated_at": "2026-06-01T00:00:00+00:00",
                "fetched_at": "2026-06-01T00:00:00+00:00",
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": {"provider": "FRED", "source_series": series},
            },
            db_path=db_path,
        )
    return db_path


def _evidence_row(
    metric_key,
    value,
    *,
    status="ok",
    source_badge="official",
    ai_context_allowed=True,
    interpretation_hint="test",
):
    return DashboardEvidenceRow(
        row_id=f"liquidity_funding_stress:{metric_key}",
        module="liquidity_funding_stress",
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value) if value is not None else "research needed",
        unit=None,
        status=status,
        source="FRED" if source_badge != "derived" else "market_history",
        source_badge=source_badge,
        source_series=metric_key.upper(),
        observation_date="2026-06-01",
        generated_at="2026-06-01T00:00:00+00:00",
        freshness_status="historical",
        missing_reason="source_mapping_required" if status == "research_needed" else None,
        interpretation_hint=interpretation_hint,
        blocked_reason=None if ai_context_allowed else f"status_{status}",
        ai_context_allowed=ai_context_allowed,
        interpretation_boundary=d14.BOUNDARY,
    )


def _simple_row(module, metric_key, value, *, badge="official"):
    return {
        "module": module,
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value,
        "value_text": str(value),
        "unit": None,
        "status": "ok",
        "source": "FRED" if badge != "derived" else "market_history",
        "source_badge": badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": "Derived from local market history." if badge == "derived" else "test",
        "ai_context_allowed": True,
    }


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}
