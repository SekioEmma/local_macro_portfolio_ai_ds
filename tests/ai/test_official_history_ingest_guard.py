from __future__ import annotations

import importlib.util
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app_backend.services.official_history_ingest_guard import (
    OfficialHistoryAdmissionError,
    list_approved_history_routes,
    resolve_approved_history_route,
    validate_history_batch,
    validate_history_observation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    script = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fred_record(metric_key: str = "dgs10", source_series: str = "DGS10", **overrides):
    record = {
        "metric_key": metric_key,
        "observation_date": "2026-06-18",
        "value": 4.25,
        "value_text": "4.25",
        "unit": "percent",
        "status": "ok",
        "source": "FRED",
        "source_badge": "official_fallback",
        "provider": "fred",
        "source_series": source_series,
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "raw",
        "lineage": {"source_series": source_series},
    }
    record.update(overrides)
    return record


def _bls_index_record(
    metric_key: str = "headline_cpi_index",
    source_series: str = "CUSR0000SA0",
    **overrides,
):
    record = {
        "metric_key": metric_key,
        "observation_date": "2026-05-01",
        "value": 321.0,
        "value_text": "321.0",
        "unit": "index",
        "status": "ok",
        "source": "BLS",
        "source_badge": "official",
        "provider": "bls",
        "source_series": source_series,
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "raw",
        "lineage": {"source_series": source_series},
    }
    record.update(overrides)
    return record


def _bls_yoy_record(
    metric_key: str = "headline_cpi_yoy",
    source_series: str = "CUSR0000SA0",
    **overrides,
):
    record = _bls_index_record(metric_key=metric_key, source_series=source_series)
    record.update(
        {
            "value": 3.1,
            "value_text": "3.1000",
            "unit": "percent_yoy",
            "metric_kind": "derived",
            "lineage": {
                "source_series": source_series,
                "prior_observation_date": "2025-05-01",
            },
        }
    )
    record.update(overrides)
    return record


def _assert_rejected(route_key: str, record: dict, code: str) -> None:
    with pytest.raises(OfficialHistoryAdmissionError) as exc_info:
        validate_history_observation(route_key, record)
    assert exc_info.value.code == code
    assert str(exc_info.value) == code


def test_list_routes_is_fixed_and_immutable() -> None:
    routes = list_approved_history_routes()
    assert tuple(route.route_key for route in routes) == ("fred_rates", "bls_cpi")
    with pytest.raises(FrozenInstanceError):
        routes[0].route_key = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        routes[0].series[0].metric_key = "changed"  # type: ignore[misc]


def test_fred_catalog_matches_existing_ingest_script() -> None:
    ingest = _load_script("ingest_official_rates_history")
    route = resolve_approved_history_route("fred_rates")
    assert {
        item.source_series: item.metric_key for item in route.series
    } == {
        series_id: config["metric_key"]
        for series_id, config in ingest.RATE_SERIES.items()
    }


def test_bls_catalog_matches_existing_ingest_script() -> None:
    ingest = _load_script("ingest_official_bls_cpi_history")
    route = resolve_approved_history_route("bls_cpi")
    metrics_by_series = {}
    for item in route.series:
        metrics_by_series.setdefault(item.source_series, set()).add(item.metric_key)
    assert metrics_by_series == {
        series_id: {config["index_metric_key"], config["yoy_metric_key"]}
        for series_id, config in ingest.BLS_CPI_SERIES.items()
    }


@pytest.mark.parametrize(
    ("series_id", "metric_key"),
    [
        ("DGS2", "dgs2"),
        ("DGS10", "dgs10"),
        ("DGS30", "dgs30"),
        ("T10Y2Y", "t10y2y"),
        ("T10YIE", "t10yie"),
        ("DFII10", "dfii10"),
    ],
)
def test_all_fred_rate_records_are_allowed(series_id: str, metric_key: str) -> None:
    record = _fred_record(metric_key=metric_key, source_series=series_id)
    assert validate_history_observation("fred_rates", record) == record


@pytest.mark.parametrize(
    ("series_id", "index_key", "yoy_key"),
    [
        ("CUSR0000SA0", "headline_cpi_index", "headline_cpi_yoy"),
        ("CUSR0000SA0L1E", "core_cpi_index", "core_cpi_yoy"),
    ],
)
def test_bls_index_and_yoy_records_are_allowed(
    series_id: str,
    index_key: str,
    yoy_key: str,
) -> None:
    assert validate_history_observation(
        "bls_cpi", _bls_index_record(index_key, series_id)
    )["metric_kind"] == "raw"
    assert validate_history_observation(
        "bls_cpi", _bls_yoy_record(yoy_key, series_id)
    )["metric_kind"] == "derived"


def test_validate_batch_returns_safe_tuple() -> None:
    batch = validate_history_batch(
        "fred_rates",
        [_fred_record("dgs2", "DGS2"), _fred_record("dgs10", "DGS10")],
    )
    assert isinstance(batch, tuple)
    assert [row["metric_key"] for row in batch] == ["dgs2", "dgs10"]


@pytest.mark.parametrize(
    ("route_key", "record", "code"),
    [
        ("missing_route", _fred_record(), "unsupported_route"),
        ("fred_rates", _fred_record(metric_key="not_allowed"), "unsupported_metric_key"),
        ("fred_rates", _fred_record(provider="bls"), "provider_mismatch"),
        ("fred_rates", _fred_record(source="BLS"), "source_mismatch"),
        ("fred_rates", _fred_record(source_badge="official"), "source_badge_mismatch"),
        ("fred_rates", _fred_record(source_series="DGS1"), "source_series_mismatch"),
        ("fred_rates", _fred_record(status="missing"), "status_not_ok"),
        ("fred_rates", _fred_record(freshness_status="stale"), "freshness_status_mismatch"),
        ("fred_rates", _fred_record(ai_context_allowed=False), "ai_context_not_allowed"),
        ("fred_rates", _fred_record(observation_date="2026-13-01"), "invalid_observation_date"),
        ("fred_rates", _fred_record(observation_date=None), "invalid_observation_date"),
        ("fred_rates", _fred_record(value=math.nan), "invalid_numeric_value"),
        ("fred_rates", _fred_record(value=math.inf), "invalid_numeric_value"),
        ("fred_rates", _fred_record(value="4.25"), "invalid_numeric_value"),
        ("fred_rates", _fred_record(value=None), "invalid_numeric_value"),
        ("fred_rates", _fred_record(metric_kind="derived"), "invalid_metric_kind"),
        ("bls_cpi", _bls_index_record(source_badge="official_fallback"), "source_badge_mismatch"),
        ("bls_cpi", _bls_index_record(source_badge="search-derived"), "source_badge_mismatch"),
        ("bls_cpi", _bls_index_record(source_badge="proxy"), "source_badge_mismatch"),
        ("bls_cpi", _bls_yoy_record(lineage={}), "missing_derived_lineage"),
        (
            "bls_cpi",
            _bls_yoy_record(lineage={"source_series": "CUSR0000SA0"}),
            "missing_derived_lineage",
        ),
        (
            "bls_cpi",
            _bls_yoy_record(lineage={"prior_observation_date": "not-a-date"}),
            "missing_derived_lineage",
        ),
        ("bls_cpi", _bls_yoy_record(metric_kind="raw"), "invalid_metric_kind"),
        ("bls_cpi", _bls_index_record(metric_kind="derived"), "invalid_metric_kind"),
        ("bls_cpi", _bls_yoy_record(source_series="CUSR0000SA0L1E"), "source_series_mismatch"),
    ],
)
def test_rejects_invalid_records(route_key: str, record: dict, code: str) -> None:
    _assert_rejected(route_key, record, code)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "https://fred.stlouisfed.org/series/DGS10"),
        ("source_url", "https://www.bls.gov/cpi/"),
        ("source_link", "https://www.reuters.com/markets/"),
        ("web_url", "https://www.bloomberg.com/markets"),
        ("search_url", "https://tavily.example/search"),
        ("provider_url", "https://api.bls.gov/publicAPI/v1/timeseries/data/"),
    ],
)
def test_rejects_any_url_input(field: str, value: str) -> None:
    _assert_rejected("fred_rates", _fred_record(**{field: value}), "url_input_not_allowed")


@pytest.mark.parametrize(
    "value",
    [
        "https://fred.stlouisfed.org/series/DGS10",
        "https://www.bls.gov/cpi/",
        "https://www.reuters.com/markets/",
        "https://www.bloomberg.com/markets/",
        "https://tavily.example/search",
    ],
)
def test_rejects_url_like_values_anywhere(value: str) -> None:
    _assert_rejected(
        "fred_rates",
        _fred_record(lineage={"source_series": "DGS10", "note": value}),
        "url_input_not_allowed",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"raw_provider_payload": {"data": []}},
        {"raw_prompt": "prompt"},
        {"raw_output": "output"},
        {"account_id": "123"},
        {"position": "SPY 50%"},
        {"transaction": "buy"},
        {"notes": "contains API_KEY inside"},
        {"lineage": {"raw_payload": "payload"}},
        {"lineage": {"holdings": "private"}},
    ],
)
def test_rejects_sensitive_keys_or_values(payload: dict) -> None:
    _assert_rejected(
        "fred_rates",
        _fred_record(**payload),
        "sensitive_content_rejected",
    )


def test_validate_batch_fails_closed_on_any_bad_record() -> None:
    with pytest.raises(OfficialHistoryAdmissionError) as exc_info:
        validate_history_batch(
            "fred_rates",
            [
                _fred_record("dgs2", "DGS2"),
                _fred_record("dgs10", "DGS10", source_badge="official"),
            ],
        )
    assert exc_info.value.code == "source_badge_mismatch"


def test_guard_source_has_no_runtime_or_network_hooks() -> None:
    source = (
        REPO_ROOT
        / "src"
        / "app_backend"
        / "services"
        / "official_history_ingest_guard.py"
    ).read_text(encoding="utf-8")
    forbidden_tokens = [
        "httpx",
        "requests",
        "aiohttp",
        "sqlite3",
        "socket",
        "open(",
        "os.environ",
        "os.getenv",
        "FastAPI",
        "main.py",
    ]
    assert not any(token in source for token in forbidden_tokens)


def test_production_guard_does_not_import_ingest_scripts() -> None:
    source = (
        REPO_ROOT
        / "src"
        / "app_backend"
        / "services"
        / "official_history_ingest_guard.py"
    ).read_text(encoding="utf-8")
    assert "ingest_official_rates_history" not in source
    assert "ingest_official_bls_cpi_history" not in source
