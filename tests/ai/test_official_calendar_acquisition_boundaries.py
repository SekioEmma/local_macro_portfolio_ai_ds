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


# ===========================================================================
# C4c: Boundary source scan additions
# ===========================================================================

def test_acquisition_service_no_urllib():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "urllib" not in source


def test_acquisition_service_no_sqlite3():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "sqlite3" not in source


def test_acquisition_service_no_os_getenv():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "os.getenv" not in source
    assert "os.environ" not in source


def test_acquisition_service_no_rag_embedding_vector():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for token in ["RAG", "embedding", "vector_store", "VectorStore", "DeepSeek", "deepseek", "Tavily", "tavily"]:
        assert token not in source, f"{token!r} found in acquisition service"


def test_acquisition_service_no_provider_payload_import():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for token in ["knowledge_base", "FetchedOfficialCalendarPayload", "SearchResult"]:
        assert token not in source, f"{token!r} found in acquisition service"


def test_summary_no_new_forbidden_fields():
    from dataclasses import fields as dc_fields
    from app_backend.services.official_calendar_acquisition_service import OfficialCalendarAcquisitionSummary
    names = {f.name for f in dc_fields(OfficialCalendarAcquisitionSummary)}
    forbidden = {"url", "body", "raw_payload", "headers", "db_path", "exception", "traceback", "raw_body"}
    overlap = names & forbidden
    assert not overlap, f"Forbidden fields found: {overlap}"


def test_sources_still_only_bls_and_bea():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert '"bls"' in source
    assert '"bea"' in source
    # No other sources silently added
    for forbidden_source in ['"fred"', '"fomc"', '"fed"', '"imf"', '"wsj"']:
        assert forbidden_source not in source, f"{forbidden_source} found in acquisition service"


def test_fomc_still_in_unavailable_not_transport():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "fomc_statement" in source
    # Must be in unavailable list, not a new fetch path
    assert "federalreserve" not in source.lower()
    assert "fomc_transport" not in source


def test_no_new_api_route_in_main():
    source = _read("src/app_backend/main.py")
    assert "acquisition" not in source.lower()
    assert "c4c" not in source.lower()


def test_no_scheduler_or_background_in_acquisition():
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for token in ["schedule", "cron", "background", "daemon", "asyncio", "threading"]:
        assert token not in source.lower(), f"{token!r} found in acquisition service"


# ===========================================================================
# C4e: Exception-total boundary source scan
# ===========================================================================


def test_c4e_acquisition_service_does_not_catch_base_exception():
    """The acquisition service must never catch BaseException — only Exception."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "BaseException" not in source


def test_c4e_validate_mutation_counts_helper_present():
    """The C4e writer-count normalizer must be present and exported under its new name."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "_validate_mutation_counts" in source


def test_c4e_legacy_validate_mutation_result_removed():
    """The legacy bool-returning helper must be replaced by the count-returning normalizer."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "def _validate_mutation_result" not in source


def test_c4e_success_summary_uses_captured_counts_not_mutation_attrs():
    """The success summary must not re-access mutation.* attributes after validation."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for forbidden in [
        "mutation.event_count",
        "mutation.created_count",
        "mutation.updated_count",
    ]:
        assert forbidden not in source, (
            f"{forbidden!r} found in acquisition service — success summary "
            "must use only the helper-returned primitive counts (C4e TOCTOU)."
        )


def test_c4e_payload_strict_builtin_str_for_content_type_and_body():
    """Content type and body must be checked with exact `type() is str`, not isinstance,
    so str subclasses cannot override .split / .strip / .lower / .encode."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "type(content_type) is not str" in source
    assert "type(body) is not str" in source


def test_c4e_mutation_result_exact_type_check():
    """The mutation-count helper must use exact-type check, not isinstance, so
    subclasses cannot override attribute access."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    assert "type(result) is not EconomicCalendarMutationResult" in source


def test_c4e_acquisition_service_no_new_forbidden_imports():
    """No new network / persistence / AI / search imports may sneak in via C4e."""
    source = _read("src/app_backend/services/official_calendar_acquisition_service.py")
    for token in [
        "httpx",
        "requests",
        "aiohttp",
        "urllib",
        "sqlite3",
        "os.getenv",
        "os.environ",
        "Tavily",
        "tavily",
        "DeepSeek",
        "deepseek",
        "RAG",
        "embedding",
        "VectorStore",
        "vector_store",
        "FastAPI",
        "APIRouter",
        "scheduler",
        "background",
    ]:
        assert token not in source, f"{token!r} found in acquisition service"


def test_c4e_public_summary_repr_clean_of_secrets():
    """The summary dataclass must expose no field that could carry raw payload,
    URL, exception, traceback, or DB path."""
    from dataclasses import fields as dc_fields

    from app_backend.services.official_calendar_acquisition_service import (
        OfficialCalendarAcquisitionSummary,
    )

    names = {f.name for f in dc_fields(OfficialCalendarAcquisitionSummary)}
    forbidden = {
        "url",
        "raw_body",
        "raw_payload",
        "headers",
        "response",
        "db_path",
        "exception",
        "traceback",
        "stack",
        "body",
        "payload",
    }
    assert not names & forbidden
