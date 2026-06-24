from __future__ import annotations

import json
from pathlib import Path

import pytest

from app_backend.services import official_history_ingest_service as service_module
from app_backend.services.official_history_ingest_guard import OfficialHistoryAdmissionError
from app_backend.services.official_history_ingest_service import (
    OfficialHistoryIngestService,
    build_default_official_history_ingest_service,
)


FRED_SERIES = ("DGS2", "DGS10", "DGS30", "T10Y2Y", "T10YIE", "DFII10")
BLS_SERIES = ("CUSR0000SA0", "CUSR0000SA0L1E")
_DEFAULT_WRITER_RESULT = object()


class RecordingDeps:
    def __init__(self) -> None:
        self.fred_calls: list[tuple[str, int]] = []
        self.bls_calls: list[tuple[tuple[str, ...], int, int]] = []
        self.writer_calls: list[list[dict]] = []
        self.raise_writer = False
        self.writer_result = _DEFAULT_WRITER_RESULT

    def fred_reader(self, series_id: str, limit: int) -> dict:
        self.fred_calls.append((series_id, limit))
        return {
            "status": "ok",
            "series_id": series_id,
            "timestamp": "2026-06-24T00:00:00+00:00",
            "data": [{"date": "2026-06-18", "value": "4.25"}],
        }

    def bls_reader(self, series_ids: list[str], start_year: int, end_year: int) -> dict:
        self.bls_calls.append((tuple(series_ids), start_year, end_year))
        return {
            "status": "ok",
            "retrieved_at": "2026-06-24T00:00:00+00:00",
            "series": [
                {
                    "seriesID": series_id,
                    "seriesTitle": (
                        "CPI-U All items in U.S. city average, seasonally adjusted"
                        if series_id == "CUSR0000SA0"
                        else "CPI-U less food and energy in U.S. city average"
                    ),
                    "data": [
                        {"year": "2025", "period": "M05", "value": "300.0"},
                        {"year": "2026", "period": "M05", "value": "309.0"},
                    ],
                }
                for series_id in series_ids
            ],
        }

    def writer(self, observations: list[dict]) -> dict[str, int]:
        self.writer_calls.append(list(observations))
        if self.raise_writer:
            raise RuntimeError("raw writer failure with secret")
        if self.writer_result is not _DEFAULT_WRITER_RESULT:
            return self.writer_result
        return {"observation_count": len(observations), "inserted_count": len(observations), "updated_count": 0}


def _service(deps: RecordingDeps) -> OfficialHistoryIngestService:
    return OfficialHistoryIngestService(
        fred_reader=deps.fred_reader,
        bls_window_reader=deps.bls_reader,
        history_writer=deps.writer,
        now_provider=lambda: "2026-06-24T00:00:00+00:00",
    )


def _fred_payload(series_id: str, data: list[dict] | None = None) -> dict:
    return {
        "status": "ok",
        "series_id": series_id,
        "timestamp": "2026-06-24T00:00:00+00:00",
        "data": data if data is not None else [{"date": "2026-06-18", "value": "4.25"}],
    }


def _bls_series_payload(series_id: str, data: list[dict] | None = None) -> dict:
    return {
        "seriesID": series_id,
        "seriesTitle": (
            "CPI-U All items in U.S. city average, seasonally adjusted"
            if series_id == "CUSR0000SA0"
            else "CPI-U less food and energy in U.S. city average"
        ),
        "data": data
        if data is not None
        else [
            {"year": "2025", "period": "M05", "value": "300.0"},
            {"year": "2026", "period": "M05", "value": "309.0"},
        ],
    }


def test_construction_has_zero_reader_or_writer_side_effects() -> None:
    deps = RecordingDeps()
    _service(deps)
    assert deps.fred_calls == []
    assert deps.bls_calls == []
    assert deps.writer_calls == []


def test_default_factory_returns_service_without_calling_providers() -> None:
    service = build_default_official_history_ingest_service()
    assert isinstance(service, OfficialHistoryIngestService)


def test_default_factory_planned_run_does_not_need_provider_calls() -> None:
    service = build_default_official_history_ingest_service()
    summary = service.run("fred_rates", live=False, write=False)
    assert summary["status"] == "planned"
    assert summary["error_codes"] == ["live_disabled"]


def test_unsupported_route_calls_no_reader_or_writer() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("unknown", live=True, write=True)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["unsupported_route"]
    assert deps.fred_calls == deps.bls_calls == deps.writer_calls == []


def test_live_false_is_planned_and_calls_no_reader_or_writer() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("fred_rates")
    assert summary["status"] == "planned"
    assert summary["error_codes"] == ["live_disabled"]
    assert summary["planned_series"] == list(FRED_SERIES)
    assert deps.fred_calls == deps.bls_calls == deps.writer_calls == []


@pytest.mark.parametrize(
    ("route_key", "expected_series"),
    [
        ("fred_rates", list(FRED_SERIES)),
        ("bls_cpi", ["CUSR0000SA0", "CUSR0000SA0", "CUSR0000SA0L1E", "CUSR0000SA0L1E"]),
    ],
)
def test_planned_summary_for_each_route_has_catalog_only(
    route_key: str,
    expected_series: list[str],
) -> None:
    deps = RecordingDeps()
    summary = _service(deps).run(route_key, live=False)
    assert summary["status"] == "planned"
    assert summary["planned_series"] == expected_series
    assert deps.fred_calls == deps.bls_calls == deps.writer_calls == []


def test_write_without_live_is_blocked_before_route_resolution() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("fred_rates", write=True)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["write_requires_live"]
    assert deps.fred_calls == deps.bls_calls == deps.writer_calls == []


def test_fred_dry_run_uses_reader_but_not_writer() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("fred_rates", live=True, write=False, fred_limit=7)
    assert summary["status"] == "dry_run"
    assert summary["normalized_observations"] == 6
    assert summary["source_badge_distribution"] == {"official_fallback": 6}
    assert summary["metric_kind_distribution"] == {"raw": 6}
    assert deps.fred_calls == [(series_id, 7) for series_id in FRED_SERIES]
    assert deps.writer_calls == []


def test_fred_write_uses_writer_once_with_validated_observations() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["status"] == "written"
    assert summary["inserted_count"] == 6
    assert len(deps.writer_calls) == 1
    assert {row["source_badge"] for row in deps.writer_calls[0]} == {"official_fallback"}
    assert {row["metric_kind"] for row in deps.writer_calls[0]} == {"raw"}


def test_fred_writer_receives_only_approved_metric_catalog() -> None:
    deps = RecordingDeps()
    _service(deps).run("fred_rates", live=True, write=True)
    assert [row["metric_key"] for row in deps.writer_calls[0]] == [
        "dgs2",
        "dgs10",
        "dgs30",
        "t10y2y",
        "t10yie",
        "dfii10",
    ]
    assert all(row["source_badge"] != "official" for row in deps.writer_calls[0])


@pytest.mark.parametrize("write", [False, True])
def test_fred_missing_one_required_series_blocks_and_never_writes(write: bool) -> None:
    deps = RecordingDeps()

    def fred_reader(series_id: str, limit: int) -> dict:
        deps.fred_calls.append((series_id, limit))
        return _fred_payload(series_id, data=[] if series_id == "DGS10" else None)

    deps.fred_reader = fred_reader  # type: ignore[method-assign]
    summary = _service(deps).run("fred_rates", live=True, write=write)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["missing_required_series"]
    assert deps.writer_calls == []


def test_fred_all_required_series_empty_blocks_and_never_writes() -> None:
    deps = RecordingDeps()
    deps.fred_reader = lambda series_id, _limit: _fred_payload(series_id, data=[])  # type: ignore[method-assign]
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["missing_required_series"]
    assert summary["normalized_observations"] == 0
    assert deps.writer_calls == []


def test_bls_dry_run_uses_reader_but_not_writer() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run(
        "bls_cpi",
        live=True,
        write=False,
        start_year=2025,
        end_year=2026,
    )
    assert summary["status"] == "dry_run"
    assert summary["normalized_observations"] == 6
    assert summary["source_badge_distribution"] == {"official": 6}
    assert summary["metric_kind_distribution"] == {"derived": 2, "raw": 4}
    assert deps.bls_calls == [(BLS_SERIES, 2025, 2026)]
    assert deps.writer_calls == []


def test_bls_write_preserves_yoy_lineage_and_writer_once() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run(
        "bls_cpi",
        live=True,
        write=True,
        start_year=2025,
        end_year=2026,
    )
    assert summary["status"] == "written"
    assert len(deps.writer_calls) == 1
    derived_rows = [row for row in deps.writer_calls[0] if row["metric_kind"] == "derived"]
    assert len(derived_rows) == 2
    assert {row["lineage"]["prior_observation_date"] for row in derived_rows} == {"2025-05-01"}
    assert {row["source_badge"] for row in deps.writer_calls[0]} == {"official"}


def test_bls_writer_receives_only_approved_metric_catalog() -> None:
    deps = RecordingDeps()
    _service(deps).run("bls_cpi", live=True, write=True, start_year=2025, end_year=2026)
    assert {row["metric_key"] for row in deps.writer_calls[0]} == {
        "headline_cpi_index",
        "headline_cpi_yoy",
        "core_cpi_index",
        "core_cpi_yoy",
    }
    assert all(row["source_badge"] != "official_fallback" for row in deps.writer_calls[0])


@pytest.mark.parametrize("only_series_id", BLS_SERIES)
def test_bls_missing_one_required_index_series_blocks_and_never_writes(only_series_id: str) -> None:
    deps = RecordingDeps()
    deps.bls_reader = lambda _series_ids, _start, _end: {  # type: ignore[method-assign]
        "status": "ok",
        "retrieved_at": "2026-06-24T00:00:00+00:00",
        "series": [_bls_series_payload(only_series_id)],
    }
    summary = _service(deps).run("bls_cpi", live=True, write=True, start_year=2025, end_year=2026)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["missing_required_series"]
    assert deps.writer_calls == []


def test_bls_empty_series_payload_blocks_and_never_writes() -> None:
    deps = RecordingDeps()
    deps.bls_reader = lambda _series_ids, _start, _end: {  # type: ignore[method-assign]
        "status": "ok",
        "retrieved_at": "2026-06-24T00:00:00+00:00",
        "series": [],
    }
    summary = _service(deps).run("bls_cpi", live=True, write=True, start_year=2025, end_year=2026)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["missing_required_series"]
    assert summary["normalized_observations"] == 0
    assert deps.writer_calls == []


def test_bls_required_index_series_without_yoy_is_allowed_to_dry_run_and_write() -> None:
    deps = RecordingDeps()
    deps.bls_reader = lambda _series_ids, _start, _end: {  # type: ignore[method-assign]
        "status": "ok",
        "retrieved_at": "2026-06-24T00:00:00+00:00",
        "series": [
            _bls_series_payload("CUSR0000SA0", data=[{"year": "2026", "period": "M05", "value": "309.0"}]),
            _bls_series_payload("CUSR0000SA0L1E", data=[{"year": "2026", "period": "M05", "value": "318.0"}]),
        ],
    }
    dry_run = _service(deps).run("bls_cpi", live=True, write=False, start_year=2026, end_year=2026)
    written = _service(deps).run("bls_cpi", live=True, write=True, start_year=2026, end_year=2026)
    assert dry_run["status"] == "dry_run"
    assert dry_run["normalized_observations"] == 2
    assert dry_run["metric_kind_distribution"] == {"raw": 2}
    assert written["status"] == "written"
    assert written["normalized_observations"] == 2
    assert len(deps.writer_calls) == 1
    assert {row["metric_kind"] for row in deps.writer_calls[0]} == {"raw"}


def test_bls_default_end_year_comes_from_now_provider() -> None:
    deps = RecordingDeps()
    _service(deps).run("bls_cpi", live=True, start_year=2026)
    assert deps.bls_calls == [(BLS_SERIES, 2026, 2026)]


def test_bls_years_are_split_into_v1_windows() -> None:
    deps = RecordingDeps()
    _service(deps).run("bls_cpi", live=True, start_year=2000, end_year=2021)
    assert deps.bls_calls == [
        (BLS_SERIES, 2000, 2009),
        (BLS_SERIES, 2010, 2019),
        (BLS_SERIES, 2020, 2021),
    ]


@pytest.mark.parametrize(
    ("route_key", "reader_name", "payload", "code"),
    [
        (
            "fred_rates",
            "fred",
            {"status": "ok", "series_id": "DGS1", "data": []},
            "series_mismatch",
        ),
        ("fred_rates", "fred", {"status": "error", "error": "raw provider blew up"}, "provider_error"),
        ("fred_rates", "fred", {"status": "ok", "series_id": "DGS10", "data": "bad"}, "malformed_payload"),
        (
            "fred_rates",
            "fred",
            {"status": "ok", "series_id": "DGS10", "data": [{"date": "bad", "value": "1"}]},
            "invalid_observation_date",
        ),
        (
            "fred_rates",
            "fred",
            {"status": "ok", "series_id": "DGS10", "data": [{"date": "2026-01-01", "value": "bad"}]},
            "invalid_numeric_value",
        ),
        (
            "bls_cpi",
            "bls",
            {"status": "ok", "series": [{"seriesID": "BAD", "data": []}]},
            "series_mismatch",
        ),
        (
            "bls_cpi",
            "bls",
            {"status": "error", "error": "full provider secret text"},
            "provider_error",
        ),
        ("bls_cpi", "bls", {"status": "ok", "series": "bad"}, "malformed_payload"),
        (
            "bls_cpi",
            "bls",
            {
                "status": "ok",
                "series": [{"seriesID": "CUSR0000SA0", "seriesTitle": "Wrong title", "data": []}],
            },
            "title_mismatch",
        ),
        (
            "bls_cpi",
            "bls",
            {
                "status": "ok",
                "series": [{"seriesID": "CUSR0000SA0", "data": [{"year": "2026", "period": "bad", "value": "1"}]}],
            },
            "invalid_observation_date",
        ),
        (
            "bls_cpi",
            "bls",
            {
                "status": "ok",
                "series": [{"seriesID": "CUSR0000SA0", "data": [{"year": "2026", "period": "M01", "value": "bad"}]}],
            },
            "invalid_numeric_value",
        ),
    ],
)
def test_provider_and_payload_errors_are_stable(
    route_key: str,
    reader_name: str,
    payload: dict,
    code: str,
) -> None:
    deps = RecordingDeps()
    if reader_name == "fred":
        deps.fred_reader = lambda _series_id, _limit: payload  # type: ignore[method-assign]
    else:
        deps.bls_reader = lambda _series_ids, _start, _end: payload  # type: ignore[method-assign]
    summary = _service(deps).run(route_key, live=True, write=True, start_year=2026, end_year=2026)
    assert summary["status"] == "blocked"
    assert code in summary["error_codes"]
    assert deps.writer_calls == []
    serialized = json.dumps(summary, sort_keys=True)
    assert "raw provider" not in serialized
    assert "secret" not in serialized


@pytest.mark.parametrize("route_key", ["fred_rates", "bls_cpi"])
def test_reader_exception_is_safe_and_blocks_writer(route_key: str) -> None:
    deps = RecordingDeps()

    def boom(*_args):
        raise RuntimeError("provider raw exception with account secret")

    if route_key == "fred_rates":
        deps.fred_reader = boom  # type: ignore[method-assign]
    else:
        deps.bls_reader = boom  # type: ignore[method-assign]
    summary = _service(deps).run(route_key, live=True, write=True, start_year=2026, end_year=2026)
    assert summary["error_codes"] == ["provider_error"]
    assert deps.writer_calls == []
    serialized = json.dumps(summary, sort_keys=True)
    assert "account" not in serialized
    assert "secret" not in serialized


def test_admission_failure_blocks_whole_batch_and_does_not_write(monkeypatch) -> None:
    deps = RecordingDeps()

    def reject(_route_key, _observations):
        raise OfficialHistoryAdmissionError("url_input_not_allowed")

    monkeypatch.setattr(service_module, "validate_history_batch", reject)
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["url_input_not_allowed"]
    assert summary["normalized_observations"] == 6
    assert deps.writer_calls == []


@pytest.mark.parametrize(
    "code",
    ["search-derived", "proxy", "sensitive_content_rejected"],
)
def test_admission_failure_summary_is_safe(monkeypatch, code: str) -> None:
    deps = RecordingDeps()

    def reject(_route_key, _observations):
        raise OfficialHistoryAdmissionError(code)

    monkeypatch.setattr(service_module, "validate_history_batch", reject)
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["error_codes"] == [code]
    assert deps.writer_calls == []


def test_writer_exception_returns_safe_summary_without_raw_exception() -> None:
    deps = RecordingDeps()
    deps.raise_writer = True
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["write_failed"]
    serialized = json.dumps(summary, sort_keys=True)
    assert "raw writer failure" not in serialized
    assert "secret" not in serialized
    assert len(deps.writer_calls) == 1


@pytest.mark.parametrize(
    "writer_result",
    [
        None,
        [],
        ["raw writer secret"],
        {},
        {"inserted_count": 6, "updated_count": 0},
        {"observation_count": 5, "inserted_count": 5, "updated_count": 0},
        {"observation_count": 6, "inserted_count": 5, "updated_count": 0},
        {"observation_count": True, "inserted_count": 6, "updated_count": 0},
        {"observation_count": 6, "inserted_count": -1, "updated_count": 7},
        {"observation_count": "6", "inserted_count": 6, "updated_count": 0},
    ],
)
def test_malformed_writer_summary_blocks_without_reporting_written(writer_result) -> None:
    deps = RecordingDeps()
    deps.writer_result = writer_result
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["status"] == "blocked"
    assert summary["error_codes"] == ["write_failed"]
    assert len(deps.writer_calls) == 1
    serialized = json.dumps(summary, sort_keys=True)
    assert "raw writer" not in serialized
    assert "secret" not in serialized


def test_valid_writer_summary_with_matching_counts_reports_written() -> None:
    deps = RecordingDeps()
    deps.writer_result = {"observation_count": 6, "inserted_count": 2, "updated_count": 4}
    summary = _service(deps).run("fred_rates", live=True, write=True)
    assert summary["status"] == "written"
    assert summary["inserted_count"] == 2
    assert summary["updated_count"] == 4


def test_dry_run_never_calls_writer_even_with_valid_observations() -> None:
    deps = RecordingDeps()
    _service(deps).run("fred_rates", live=True, write=False)
    _service(deps).run("bls_cpi", live=True, write=False, start_year=2025, end_year=2026)
    assert deps.writer_calls == []


def test_writer_receives_no_url_or_raw_payload_fields() -> None:
    deps = RecordingDeps()
    _service(deps).run("bls_cpi", live=True, write=True, start_year=2025, end_year=2026)
    serialized = json.dumps(deps.writer_calls[0], sort_keys=True)
    for token in ["http://", "https://", "raw_payload", "raw_provider_payload", "source_url"]:
        assert token not in serialized


def test_invalid_fred_limit_blocks_before_reader() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("fred_rates", live=True, fred_limit=0)
    assert summary["error_codes"] == ["invalid_fred_limit"]
    assert deps.fred_calls == []


def test_invalid_bls_year_range_blocks_before_reader() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("bls_cpi", live=True, start_year=2027, end_year=2026)
    assert summary["error_codes"] == ["invalid_year_range"]
    assert deps.bls_calls == []


def test_output_contains_no_url_secret_or_private_terms() -> None:
    deps = RecordingDeps()
    summary = _service(deps).run("bls_cpi", live=True, start_year=2025, end_year=2026)
    serialized = json.dumps(summary, sort_keys=True)
    for token in [
        "http://",
        "https://",
        "raw_payload",
        "provider error",
        "secret",
        "holdings",
        "account",
        "position",
        "transaction",
    ]:
        assert token not in serialized


def test_service_source_has_no_external_runtime_imports() -> None:
    source = (
        Path(__file__).parents[2]
        / "src"
        / "app_backend"
        / "services"
        / "official_history_ingest_service.py"
    ).read_text(encoding="utf-8")
    forbidden_tokens = [
        "httpx",
        "requests",
        "aiohttp",
        "os.environ",
        "os.getenv",
        "sqlite3",
        "FastAPI",
        "main.py",
    ]
    assert not any(token in source for token in forbidden_tokens)
