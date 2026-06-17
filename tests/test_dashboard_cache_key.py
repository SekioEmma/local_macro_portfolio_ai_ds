import json
import os
from pathlib import Path

from app_backend.services.dashboard_cache_key import (
    CACHE_KEY_VERSION,
    build_dashboard_cache_key,
    cache_bypass_reason,
    cache_key_digest,
    cache_key_payload,
    file_signature,
)


REQUIRED_REPORT_FILES = {
    "market_snapshot": "market_snapshot.json",
    "market_temperature": "market_temperature.json",
    "portfolio_snapshot": "portfolio_snapshot.json",
    "provider_health": "provider_health_check.json",
}
OPTIONAL_REPORT_FILES = {"llm_context_pack": "llm_context_pack.json"}


def test_file_signature_missing_and_existing_files(tmp_path):
    missing = file_signature(tmp_path / "missing.json")

    assert missing.exists is False
    assert missing.size_bytes is None
    assert missing.mtime_ns is None

    existing_path = tmp_path / "market_snapshot.json"
    existing_path.write_text("abc", encoding="utf-8")
    first = file_signature(existing_path)

    assert first.exists is True
    assert first.size_bytes == 3
    assert isinstance(first.mtime_ns, int)

    existing_path.write_text("abcdef", encoding="utf-8")
    os.utime(existing_path, None)
    second = file_signature(existing_path)

    assert second.exists is True
    assert second.size_bytes == 6
    assert second != first


def test_digest_is_deterministic_and_mapping_order_independent(tmp_path):
    reports_dir = _write_reports(tmp_path / "reports")
    db_path = _write_db(tmp_path / "market_history.sqlite3")

    first = build_dashboard_cache_key(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
        required_report_files=REQUIRED_REPORT_FILES,
        optional_report_files=OPTIONAL_REPORT_FILES,
    )
    second = build_dashboard_cache_key(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
        required_report_files=dict(reversed(list(REQUIRED_REPORT_FILES.items()))),
        optional_report_files=dict(reversed(list(OPTIONAL_REPORT_FILES.items()))),
    )

    assert first.digest == second.digest
    assert cache_key_digest(cache_key_payload(first)) == first.digest
    assert first.version == CACHE_KEY_VERSION


def test_digest_changes_on_report_db_or_schema_marker_change(tmp_path):
    reports_dir = _write_reports(tmp_path / "reports")
    db_path = _write_db(tmp_path / "market_history.sqlite3")

    first = _build_key(reports_dir, db_path)

    (reports_dir / "market_snapshot.json").write_text(
        "changed-report-size", encoding="utf-8"
    )
    report_changed = _build_key(reports_dir, db_path)
    assert report_changed.digest != first.digest

    db_path.write_text("changed-db-size", encoding="utf-8")
    db_changed = _build_key(reports_dir, db_path)
    assert db_changed.digest != report_changed.digest

    schema_changed = build_dashboard_cache_key(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
        required_report_files=REQUIRED_REPORT_FILES,
        optional_report_files=OPTIONAL_REPORT_FILES,
        schema_marker="m11-dashboard-cache-key-v2",
    )
    assert schema_changed.digest != db_changed.digest


def test_required_and_optional_report_signatures(tmp_path):
    reports_dir = _write_reports(tmp_path / "reports")
    db_path = _write_db(tmp_path / "market_history.sqlite3")

    missing_optional = _build_key(reports_dir, db_path)
    missing_payload = cache_key_payload(missing_optional)
    serialized = json.dumps(missing_payload, sort_keys=True)

    for file_name in (
        "market_snapshot.json",
        "market_temperature.json",
        "portfolio_snapshot.json",
        "provider_health_check.json",
        "llm_context_pack.json",
    ):
        assert file_name in serialized
    assert missing_optional.optional_reports[0].exists is False

    (reports_dir / "llm_context_pack.json").write_text("metadata", encoding="utf-8")
    present_optional = _build_key(reports_dir, db_path)
    assert present_optional.optional_reports[0].exists is True
    assert present_optional.digest != missing_optional.digest


def test_custom_path_changes_key(tmp_path):
    reports_a = _write_reports(tmp_path / "reports_a")
    reports_b = _write_reports(tmp_path / "reports_b")
    db_a = _write_db(tmp_path / "a.sqlite3")
    db_b = _write_db(tmp_path / "b.sqlite3")

    key_a = _build_key(reports_a, db_a)
    key_reports_changed = _build_key(reports_b, db_a)
    key_db_changed = _build_key(reports_a, db_b)

    assert key_a.digest != key_reports_changed.digest
    assert key_a.digest != key_db_changed.digest


def test_cache_bypass_reason_precedence():
    assert (
        cache_bypass_reason(
            write_last_good=True,
            reports_dir_is_default=False,
            market_history_db_path_is_default=False,
        )
        == "cache_bypassed_for_write_last_good"
    )
    assert (
        cache_bypass_reason(
            write_last_good=False,
            reports_dir_is_default=False,
            market_history_db_path_is_default=True,
        )
        == "cache_bypassed_for_custom_path"
    )
    assert (
        cache_bypass_reason(
            write_last_good=False,
            reports_dir_is_default=True,
            market_history_db_path_is_default=False,
        )
        == "cache_bypassed_for_custom_path"
    )
    assert (
        cache_bypass_reason(
            write_last_good=False,
            reports_dir_is_default=True,
            market_history_db_path_is_default=True,
        )
        is None
    )


def test_private_payload_content_is_excluded_from_key_material(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    private_text = (
        "SECRET_HOLDING_LINE_ITEM PRIVATE_ACCOUNT_VALUE "
        "RAW_PROMPT_TEXT PROVIDER_SECRET"
    )
    for file_name in REQUIRED_REPORT_FILES.values():
        (reports_dir / file_name).write_text(private_text, encoding="utf-8")
    (reports_dir / "llm_context_pack.json").write_text(private_text, encoding="utf-8")
    db_path = _write_db(tmp_path / "market_history.sqlite3")

    key = _build_key(reports_dir, db_path)
    payload_text = json.dumps(cache_key_payload(key), sort_keys=True)
    key_repr = repr(key)

    for sentinel in (
        "SECRET_HOLDING_LINE_ITEM",
        "PRIVATE_ACCOUNT_VALUE",
        "RAW_PROMPT_TEXT",
        "PROVIDER_SECRET",
    ):
        assert sentinel not in key.digest
        assert sentinel not in key_repr
        assert sentinel not in payload_text


def test_no_runtime_cache_symbols_added_outside_helper():
    helper = Path("src/app_backend/services/dashboard_cache_key.py").resolve()
    production_files = [
        path
        for path in Path("src/app_backend").rglob("*.py")
        if path.resolve() != helper
    ]

    for path in production_files:
        text = path.read_text(encoding="utf-8")
        for token in (
            "SharedDashboardContextCache(",
            "_GLOBAL_DASHBOARD_CACHE",
            "cache_hit",
            "cache_miss",
        ):
            assert token not in text, f"{token!r} unexpectedly found in {path}"


def test_dashboard_cache_key_helper_has_no_forbidden_product_surfaces():
    text = Path("src/app_backend/services/dashboard_cache_key.py").read_text(
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


def _build_key(reports_dir, db_path):
    return build_dashboard_cache_key(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
        required_report_files=REQUIRED_REPORT_FILES,
        optional_report_files=OPTIONAL_REPORT_FILES,
    )


def _write_reports(reports_dir):
    reports_dir.mkdir()
    for file_name in REQUIRED_REPORT_FILES.values():
        (reports_dir / file_name).write_text(file_name, encoding="utf-8")
    return reports_dir


def _write_db(db_path):
    db_path.write_text("db", encoding="utf-8")
    return db_path
