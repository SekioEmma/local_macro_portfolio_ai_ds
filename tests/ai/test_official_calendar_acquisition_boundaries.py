from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ---- httpx only in transport ----

def test_httpx_only_in_transport():
    transport = _read("src/data_providers/official_calendar_real_transport.py")
    assert "import httpx" in transport


def test_parsers_no_httpx():
    source = _read("src/app_backend/services/official_calendar_parsers.py")
    assert "httpx" not in source


def test_acquisition_service_no_httpx():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "httpx" not in source


def test_cli_no_httpx():
    source = _read("scripts/ingest_official_economic_calendar.py")
    assert "httpx" not in source


# ---- transport only fixed two official URLs ----

def test_transport_fixed_bls_url():
    source = _read("src/data_providers/official_calendar_real_transport.py")
    assert "https://www.bls.gov/schedule/news_release/bls.ics" in source


def test_transport_fixed_bea_url():
    source = _read("src/data_providers/official_calendar_real_transport.py")
    assert "https://apps.bea.gov/API/signup/release_dates.json" in source


def test_transport_no_other_urls():
    source = _read("src/data_providers/official_calendar_real_transport.py")
    urls = re.findall(r"https://[^\s\"']+", source)
    allowed = {
        "https://www.bls.gov/schedule/news_release/bls.ics",
        "https://apps.bea.gov/API/signup/release_dates.json",
    }
    assert set(urls) == allowed


# ---- service / parser / CLI no network import ----

def test_parsers_no_network_imports():
    source = _read("src/app_backend/services/official_calendar_parsers.py")
    for token in ["httpx", "requests", "aiohttp", "socket", "urllib"]:
        assert token not in source


def test_acquisition_service_no_network_imports():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for token in ["httpx", "requests", "aiohttp", "socket"]:
        assert token not in source


# ---- no env / config / API key ----

def test_transport_no_env():
    source = _read("src/data_providers/official_calendar_real_transport.py")
    for token in ["os.environ", "os.getenv", "dotenv", "load_dotenv", "API_KEY"]:
        assert token not in source


def test_parsers_no_env():
    source = _read("src/app_backend/services/official_calendar_parsers.py")
    for token in ["os.environ", "os.getenv", "dotenv", "API_KEY", "config"]:
        assert token not in source


def test_acquisition_service_no_env():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for token in ["os.environ", "os.getenv", "dotenv", "API_KEY"]:
        assert token not in source


def test_cli_no_env():
    source = _read("scripts/ingest_official_economic_calendar.py")
    for token in ["os.environ", "os.getenv", "dotenv", "API_KEY"]:
        assert token not in source


# ---- no Fed URL ----

def test_transport_no_fed_url():
    source = _read("src/data_providers/official_calendar_real_transport.py")
    assert "federalreserve.gov" not in source
    assert "fed.gov" not in source.lower()


def test_parsers_no_fed():
    source = _read("src/app_backend/services/official_calendar_parsers.py")
    assert "federalreserve.gov" not in source
    assert "fomc" not in source.lower()


# ---- no Tavily / SearchResult / provider payload ----

def test_no_tavily_in_c4b_files():
    for path in [
        "src/data_providers/official_calendar_real_transport.py",
        "src/app_backend/services/official_calendar_parsers.py",
        "src/app_backend/services/official_calendar_acquisition_service.py",
        "scripts/ingest_official_economic_calendar.py",
    ]:
        source = _read(path)
        for token in ["Tavily", "SearchResult", "tavily", "search_result"]:
            assert token not in source, f"{token} found in {path}"


# ---- no API / frontend / scheduler / background ----

def test_no_api_or_frontend_in_c4b():
    for path in [
        "src/data_providers/official_calendar_real_transport.py",
        "src/app_backend/services/official_calendar_parsers.py",
        "src/app_backend/services/official_calendar_acquisition_service.py",
    ]:
        source = _read(path)
        for token in ["FastAPI", "APIRouter", "app_frontend", "scheduler", "background", "cron"]:
            assert token not in source, f"{token} found in {path}"


# ---- C4a seed tracked and production not reading ----

def test_seed_json_tracked():
    assert (ROOT / "data" / "economic_calendar_seed.json").exists()


def test_acquisition_service_no_seed_read():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "seed" not in source.lower()


# ---- public summary / record no URL, raw body, SQLite path ----

def test_summary_dataclass_no_url_field():
    from dataclasses import fields as dc_fields
    from app_backend.services.official_calendar_acquisition_service import OfficialCalendarAcquisitionSummary
    names = {f.name for f in dc_fields(OfficialCalendarAcquisitionSummary)}
    forbidden = {"url", "raw_body", "raw_payload", "db_path", "headers", "response"}
    assert not names & forbidden


# ---- docs state C4b source scope and FOMC deferred ----

def test_closeout_doc_states_bls_bea_only():
    doc = _read("docs/infra/era2_official_calendar_acquisition_closeout.md")
    assert "BLS" in doc
    assert "BEA" in doc


def test_closeout_doc_states_fomc_deferred():
    doc = _read("docs/infra/era2_official_calendar_acquisition_closeout.md")
    assert "FOMC" in doc
    assert "deferred" in doc.lower() or "不采集" in doc


def test_roadmap_marks_c4b_complete():
    roadmap = _read("docs/ROADMAP.md")
    assert "C4b" in roadmap


def test_roadmap_states_fomc_deferred():
    roadmap = _read("docs/ROADMAP.md")
    assert "FOMC" in roadmap


# ---- did not modify forbidden files ----

def test_contracts_not_modified():
    source = _read("src/app_backend/services/economic_calendar_contracts.py")
    assert "EconomicCalendarEventKey" in source
    assert "FOMC_STATEMENT" in source


def test_schema_not_modified():
    source = _read("src/app_backend/services/economic_calendar_schema.sql")
    assert "economic_calendar" in source


def test_main_py_no_c4b_route():
    source = _read("src/app_backend/main.py")
    assert "ingest" not in source.lower()
    assert "calendar_acquisition" not in source


def test_no_frontend_changes():
    app_tsx = _read("app_frontend/src/App.tsx")
    assert "calendar" not in app_tsx.lower()
