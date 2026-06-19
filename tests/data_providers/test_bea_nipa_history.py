from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from data_providers import bea_history_provider
from data_providers.source_registry import prefer_source


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_official_bea_nipa_history.py"
SPEC = importlib.util.spec_from_file_location("ingest_official_bea_nipa_history", SCRIPT)
assert SPEC and SPEC.loader
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


def test_bea_request_parameter_construction():
    params = bea_history_provider.build_bea_getdata_params(
        api_key="secret", table="T20804", frequency="M", year="2025"
    )
    assert params["method"] == "GETDATA"
    assert params["datasetname"] == "NIPA"
    assert params["TableName"] == "T20804"
    assert params["Frequency"] == "M"
    assert params["Year"] == "2025"
    discovery = bea_history_provider.build_bea_discovery_params(api_key="secret")
    assert discovery["method"] == "GETPARAMETERVALUES"
    assert discovery["ParameterName"] == "TableName"


def test_discovery_normalization():
    payload = {
        "BEAAPI": {
            "Results": {
                "ParamValue": [
                    {"Key": "T10101", "Desc": "Percent Change From Preceding Period in Real GDP"},
                    {"TableName": "T20804", "Description": "Price Indexes for PCE"},
                ]
            }
        }
    }
    assert bea_history_provider.normalize_discovery(payload) == [
        {
            "table": "T10101",
            "description": "Percent Change From Preceding Period in Real GDP",
        },
        {"table": "T20804", "description": "Price Indexes for PCE"},
    ]


def test_confirmed_mapping_registry_and_frequency_normalization():
    assert set(bea_history_provider.BEA_NIPA_MAPPINGS) == {
        "headline_pce_yoy",
        "core_pce_yoy",
        "real_gdp_qoq_saaar",
    }
    payload = {
        "BEAAPI": {
            "Results": {
                "Data": [
                    {
                        "TableName": "T10101",
                        "LineNumber": "1",
                        "TimePeriod": "2025Q4",
                        "DataValue": "1.4",
                        "LineDescription": "Gross domestic product",
                        "SeriesCode": "A191RL",
                    }
                ]
            }
        }
    }
    rows = bea_history_provider.normalize_table_rows(
        payload,
        metric_key="real_gdp_qoq_saaar",
        ingested_at="now",
    )
    assert rows[0]["observation_date"] == "2025-10-01"
    assert rows[0]["value"] == 1.4


def test_pce_yoy_calculation_and_market_observation():
    base = {
        "metric_key": "headline_pce_yoy",
        "source_metric_key": "headline_pce_index",
        "table": "T20804",
        "line": "1",
        "frequency": "M",
        "unit": "percent_yoy",
        "transform": "yoy",
        "line_description": "Personal consumption expenditures (PCE)",
        "series_code": "DPCERD3M086SBEA",
        "ingested_at": "now",
    }
    rows = [
        {**base, "observation_date": "2024-01-01", "value": 100.0},
        {**base, "observation_date": "2025-01-01", "value": 102.5},
    ]
    derived = bea_history_provider.calculate_bea_metric(rows)
    assert derived[0]["value"] == pytest.approx(2.5)
    observation = ingest.build_market_observation(derived[0])
    assert observation["source_badge"] == "official"
    assert observation["provider"] == "bea"
    assert observation["lineage"]["trigger_eligibility"] == "eligible"


def test_bea_official_priority_over_fred():
    assert prefer_source("official", "official_fallback") is True


def test_ingest_groups_table_requests_and_writes(tmp_path):
    def requester(params):
        table = params["TableName"]
        if table == "T20804":
            data = []
            for line, description in (
                ("1", "Personal consumption expenditures (PCE)"),
                ("25", "PCE excluding food and energy"),
            ):
                data.extend(
                    [
                        {
                            "TableName": table,
                            "LineNumber": line,
                            "TimePeriod": "2024M01",
                            "DataValue": "100",
                            "LineDescription": description,
                            "SeriesCode": f"S{line}",
                        },
                        {
                            "TableName": table,
                            "LineNumber": line,
                            "TimePeriod": "2025M01",
                            "DataValue": "103",
                            "LineDescription": description,
                            "SeriesCode": f"S{line}",
                        },
                    ]
                )
        else:
            data = [
                {
                    "TableName": "T10101",
                    "LineNumber": "1",
                    "TimePeriod": "2025Q1",
                    "DataValue": "2.1",
                    "LineDescription": "Gross domestic product",
                    "SeriesCode": "A191RL",
                }
            ]
        return {
            "status": "ok",
            "retrieved_at": "2026-06-19T00:00:00+00:00",
            "payload": {"BEAAPI": {"Results": {"Data": data}}},
        }

    summary = ingest.build_ingest_summary(
        db_path=tmp_path / "market.sqlite3",
        dry_run=False,
        live=True,
        requester=requester,
        api_key="test",
    )
    assert summary["inserted_count"] == 3
    assert summary["errors"] == []
