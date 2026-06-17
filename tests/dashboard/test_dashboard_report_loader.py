"""Characterization tests for the dashboard report loader.

Locks the JSON decoding behavior — including UTF-8 BOM tolerance — and the
ReportState contract before further extraction phases proceed.
"""

from pathlib import Path

from app_backend.services.dashboard_report_loader import (
    OPTIONAL_METADATA_REPORT_FILES,
    REPORT_FILES,
    ReportState,
    load_dashboard_reports,
    load_report,
)


def test_load_report_missing_file_marks_exists_false(tmp_path):
    state = load_report("market_snapshot", tmp_path / "missing.json")
    assert state.name == "market_snapshot"
    assert state.exists is False
    assert state.data is None
    assert state.error_summary is None


def test_load_report_invalid_json_returns_error_summary(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    state = load_report("market_snapshot", path)
    assert state.exists is True
    assert state.data is None
    assert state.error_summary == "bad.json is invalid or unreadable"


def test_load_report_non_object_json_returns_error_summary(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    state = load_report("market_snapshot", path)
    assert state.exists is True
    assert state.data is None
    assert state.error_summary == "list.json is not a JSON object"


def test_load_report_tolerates_utf8_bom(tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"status": "ok"}')
    state = load_report("market_snapshot", path)
    assert state.exists is True
    assert state.data == {"status": "ok"}
    assert state.error_summary is None


def test_load_dashboard_reports_loads_required_files(tmp_path):
    for key, file_name in REPORT_FILES.items():
        (tmp_path / file_name).write_text(f'{{"status": "ok", "key": "{key}"}}', encoding="utf-8")
    reports = load_dashboard_reports(tmp_path)
    assert set(reports) == set(REPORT_FILES)
    for key in REPORT_FILES:
        assert reports[key].exists is True
        assert reports[key].data["key"] == key


def test_load_dashboard_reports_skips_missing_optional(tmp_path):
    for key, file_name in REPORT_FILES.items():
        (tmp_path / file_name).write_text('{"status": "ok"}', encoding="utf-8")
    reports = load_dashboard_reports(tmp_path)
    for optional_key in OPTIONAL_METADATA_REPORT_FILES:
        assert optional_key not in reports


def test_load_dashboard_reports_includes_optional_when_present(tmp_path):
    for key, file_name in REPORT_FILES.items():
        (tmp_path / file_name).write_text('{"status": "ok"}', encoding="utf-8")
    for key, file_name in OPTIONAL_METADATA_REPORT_FILES.items():
        (tmp_path / file_name).write_text(f'{{"optional": "{key}"}}', encoding="utf-8")
    reports = load_dashboard_reports(tmp_path)
    for optional_key in OPTIONAL_METADATA_REPORT_FILES:
        assert reports[optional_key].exists is True
        assert reports[optional_key].data == {"optional": optional_key}


def test_report_state_is_frozen_dataclass():
    state = ReportState(name="x", path=Path("."), exists=False)
    try:
        state.exists = True  # type: ignore[misc]
        assert False, "ReportState should be frozen"
    except Exception:
        pass


def test_dashboard_service_reexports_report_loader_symbols():
    from app_backend.services import dashboard_service
    from app_backend.services import dashboard_report_loader

    assert dashboard_service.ReportState is dashboard_report_loader.ReportState
    assert dashboard_service.REPORT_FILES is dashboard_report_loader.REPORT_FILES
    assert (
        dashboard_service.OPTIONAL_METADATA_REPORT_FILES
        is dashboard_report_loader.OPTIONAL_METADATA_REPORT_FILES
    )
    assert dashboard_service._load_report is dashboard_report_loader.load_report
    assert (
        dashboard_service._load_dashboard_reports
        is dashboard_report_loader.load_dashboard_reports
    )
