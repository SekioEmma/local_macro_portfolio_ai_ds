from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_gitignore_ignores_calendar_db_sidecars_but_not_seed_fixture() -> None:
    gitignore = _read(".gitignore")
    assert "data/economic_calendar.sqlite" in gitignore
    assert "data/economic_calendar.sqlite-*" in gitignore
    assert "data/economic_calendar_seed.json" not in gitignore


def test_claude_and_governance_have_narrow_c4a_exception() -> None:
    claude = _read("CLAUDE.md")
    governance = _read("docs/GOVERNANCE.md")
    for text in [claude, governance]:
        assert "economic_calendar_service.py" in text
        assert "data/economic_calendar.sqlite" in text
        assert "data/economic_calendar_seed.json" in text
        assert "synthetic fixture-only" in text


def test_c4a_exception_does_not_relax_network_ai_or_rag_boundaries() -> None:
    combined = _read("CLAUDE.md") + "\n" + _read("docs/GOVERNANCE.md")
    for token in [
        "BLS/BEA/Federal Reserve",
        "Tavily",
        "API",
        "frontend",
        "CLI",
        "scheduler",
        "background task",
        "RAG",
        "embedding",
        "vector store",
        "Agent",
    ]:
        assert token in combined


def test_seed_fixture_is_documented_as_synthetic_fixture_only() -> None:
    seed = _read("data/economic_calendar_seed.json")
    closeout = _read("docs/infra/era2_offline_economic_calendar_closeout.md")
    assert "Offline synthetic fixture only" in seed
    assert "Service does not auto-load" in seed
    assert "synthetic fixture-only" in closeout
    assert "not real, current, or future economic schedule data" in closeout


def test_roadmap_marks_c4a_and_c4b_complete() -> None:
    roadmap = _read("docs/ROADMAP.md")
    assert "C4a" in roadmap and "calendar" in roadmap and "已完成" in roadmap
    assert "C4b" in roadmap
    assert "FOMC" in roadmap
    assert "| D | RAG 知识库" in roadmap


def test_no_api_frontend_or_ingest_script_was_added() -> None:
    assert not (ROOT / "scripts" / "ingest_economic_calendar.py").exists()
    service_source = _read("src/app_backend/services/economic_calendar_service.py")
    assert "FastAPI" not in service_source
    assert "APIRouter" not in service_source
    assert "app_frontend" not in service_source


def test_schema_has_no_calendar_value_or_signal_columns() -> None:
    schema = _read("src/app_backend/services/economic_calendar_schema.sql").lower()
    table_match = re.search(
        r"create table if not exists economic_calendar \((.*?)\);\n\ncreate index",
        schema,
        re.DOTALL,
    )
    assert table_match is not None
    table_body = table_match.group(1)
    forbidden = [
        "actual",
        "forecast",
        "previous",
        "value",
        "surprise",
        "score",
        "probability",
        "raw html",
        "raw_provider",
        "account",
        "holdings",
        "position",
        "transaction",
    ]
    assert not any(token in table_body for token in forbidden)


def test_closeout_says_no_official_acquisition_or_rag_started() -> None:
    closeout = _read("docs/infra/era2_offline_economic_calendar_closeout.md")
    assert "C4a does not fetch BLS, BEA, Federal Reserve" in closeout
    assert "Only explicit `EconomicCalendarService.upsert_events(...)` may write" in closeout
    assert "C4b is the earliest phase where official schedule acquisition can be discussed" in closeout
    assert "Phase D remains the future embedding, vector store, and RAG phase" in closeout
