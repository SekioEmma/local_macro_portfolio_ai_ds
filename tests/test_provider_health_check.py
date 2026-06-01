from run_provider_health_check import (
    _error_type,
    _missing_key_check,
    _safe_error_summary,
    overall_status,
    summarize_checks,
)


def test_summarize_checks_counts_statuses():
    checks = [
        {"key": "a", "status": "ok"},
        {"key": "b", "status": "skipped"},
        {"key": "c", "status": "error"},
        {"key": "d", "status": "ok"},
    ]

    assert summarize_checks(checks) == {"ok": 2, "skipped": 1, "error": 1}


def test_error_summary_redacts_and_truncates(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "secret-token")
    summary = _safe_error_summary(
        "request failed with api_key=secret-token and " + ("x" * 240),
        max_length=80,
    )

    assert "secret-token" not in summary
    assert "api_key=[redacted]" in summary
    assert len(summary) <= 80


def test_missing_key_check_marks_optional_provider_as_skipped(monkeypatch):
    monkeypatch.delenv("BEA_API_KEY", raising=False)

    result = _missing_key_check("bea_pce", "BEA")

    assert result["status"] == "skipped"
    assert result["error_type"] == "missing_key"
    assert "BEA_API_KEY" in result["error_summary"]


def test_rate_limit_error_type_is_specific():
    assert _error_type("Too Many Requests. Rate limited. Try after a while.") == "rate_limited"


def test_overall_status_ignores_missing_optional_keys():
    checks = [
        {"key": "fred_dgs10", "status": "skipped"},
        {"key": "bea_pce", "status": "skipped"},
        {"key": "treasury_10y", "status": "ok"},
        {"key": "bls_cpi", "status": "ok"},
        {"key": "ny_fed_effr", "status": "ok"},
        {"key": "yfinance_sp500", "status": "ok"},
    ]

    assert overall_status(checks) == "ok"
