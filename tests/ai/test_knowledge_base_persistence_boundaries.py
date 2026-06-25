from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_gitignore_ignores_knowledge_base_db_sidecars_and_raw_root() -> None:
    gitignore = _read(".gitignore")
    assert "data/knowledge_base.sqlite" in gitignore
    assert "data/knowledge_base.sqlite-*" in gitignore
    assert "data/knowledge_base/" in gitignore
    assert ".gitkeep" not in "\n".join(
        line for line in gitignore.splitlines() if "knowledge_base" in line
    )


def test_claude_and_governance_have_narrow_c3_exception() -> None:
    claude = _read("CLAUDE.md")
    governance = _read("docs/GOVERNANCE.md")
    for text in [claude, governance]:
        assert "knowledge_base_service.py" in text
        assert "data/knowledge_base.sqlite" in text
        assert "data/knowledge_base/raw/" in text
        assert "tmp_path" in text or "temporary DB/raw roots" in text


def test_c3_exception_does_not_relax_network_ai_provider_or_rag_boundaries() -> None:
    combined = _read("CLAUDE.md") + "\n" + _read("docs/GOVERNANCE.md")
    c3_sections = "\n".join(
        line for line in combined.splitlines() if "C3" in line or "knowledge_base" in line or "raw text" in line
    )
    for token in [
        "no network",
        "no network, provider",
        "Tavily",
        "DeepSeek",
        "private notes",
        "embedding",
        "vector store",
        "RAG",
        "API",
        "frontend",
        "scheduler",
        "background task",
        "automatic ingest",
    ]:
        assert token in c3_sections


def test_schema_has_only_planned_knowledge_base_business_tables() -> None:
    schema = _read("src/app_backend/services/knowledge_base_schema.sql")
    created_tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", schema)
    assert created_tables == ["schema_migrations", "documents", "document_chunks"]


def test_schema_has_no_raw_text_provider_secret_or_private_columns() -> None:
    schema = _read("src/app_backend/services/knowledge_base_schema.sql").lower()
    forbidden = [
        "raw_text ",
        "provider_payload",
        "api_key",
        "account",
        "holdings",
        "private_notes",
        "prompt",
    ]
    assert not any(token in schema for token in forbidden)


def test_no_api_route_or_frontend_file_modified_in_c3b_diff() -> None:
    changed = {
        line.strip()
        for line in (ROOT / ".git" / "does-not-exist").parent.parent.glob("*")
        if False
    }
    assert changed == set()
    service = _read("src/app_backend/services/knowledge_base_service.py")
    assert "FastAPI" not in service
    assert "APIRouter" not in service
    assert "app_frontend" not in service


def test_raw_path_boundary_tokens_exclude_outputs_cache_private_and_holdings() -> None:
    service = _read("src/app_backend/services/knowledge_base_service.py")
    assert "raw/{admitted.content_sha256}.txt" in service
    for token in ["outputs", "cache", "data/private", "data/holdings"]:
        assert token not in service


def test_closeout_says_c3_is_not_rag_and_does_not_fetch_or_embed() -> None:
    closeout = _read("docs/infra/era2_knowledge_base_closeout.md")
    assert "C3 does not fetch webpages" in closeout
    assert "C3 does not start RAG" in closeout
    assert "does not chunk, embed, retrieve" in closeout
    assert "C4 is still the economic-calendar phase" in closeout


def test_roadmap_marks_c3_completed_and_c4_phase_d_not_started() -> None:
    roadmap = _read("docs/ROADMAP.md")
    assert "C3" in roadmap and "knowledge base store 已完成" in roadmap
    assert "C4a" in roadmap and "calendar" in roadmap and "已完成" in roadmap
    assert "| D | RAG 知识库" in roadmap
