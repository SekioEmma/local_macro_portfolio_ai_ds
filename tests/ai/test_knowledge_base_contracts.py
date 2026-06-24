from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from hashlib import sha256
from pathlib import Path
import re

import pytest

from app_backend.services.knowledge_base_contracts import (
    AdmittedKnowledgeDocument,
    KnowledgeBaseAdmissionError,
    KnowledgeDocumentInput,
    KnowledgeDocumentType,
    admit_document,
    canonicalize_document_url,
)


SERVICE_ROOT = Path(__file__).parents[2] / "src" / "app_backend" / "services"
CONTRACT_SOURCE = SERVICE_ROOT / "knowledge_base_contracts.py"
SCHEMA_PATH = SERVICE_ROOT / "knowledge_base_schema.sql"


def _input(**overrides: str) -> KnowledgeDocumentInput:
    values = {
        "url": "https://Example.COM/reports/macro",
        "title": "Macro policy note",
        "doc_type": "policy_doc",
        "fetched_at": "2026-06-24T12:00:00+08:00",
        "raw_text": "Public macro text",
    }
    values.update(overrides)
    return KnowledgeDocumentInput(**values)


def _admit(**overrides: str) -> AdmittedKnowledgeDocument:
    return admit_document(_input(**overrides))


def _assert_rejected(code: str, **overrides: str) -> None:
    with pytest.raises(KnowledgeBaseAdmissionError) as exc_info:
        _admit(**overrides)
    assert exc_info.value.code == code
    assert str(exc_info.value) == code


@pytest.mark.parametrize("doc_type", [item.value for item in KnowledgeDocumentType])
def test_accepts_each_supported_document_type(doc_type: str) -> None:
    admitted = _admit(doc_type=doc_type)
    assert admitted.doc_type == KnowledgeDocumentType(doc_type)


@pytest.mark.parametrize("doc_type", ["discard", "unknown", "research_needed", "search-derived", "other"])
def test_rejects_unsupported_document_types(doc_type: str) -> None:
    _assert_rejected("unsupported_doc_type", doc_type=doc_type)


def test_accepts_https_url_and_derives_source_domain() -> None:
    admitted = _admit(url="https://www.Example.Org/report")
    assert admitted.canonical_url == "https://www.example.org/report"
    assert admitted.source_domain == "www.example.org"


def test_accepts_plain_hostname_without_www() -> None:
    admitted = _admit(url="https://example.org/report")
    assert admitted.source_domain == "example.org"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/report?x=1",
        "https://example.com/report#frag",
        "https://user@example.com/report",
        "https://example.com:443/report",
        "http://example.com/report",
        "file:///tmp/report",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "https://localhost/report",
        "https://sub.localhost/report",
        "https://127.0.0.1/report",
        "https://[::1]/report",
        "https://example.com/a/../b",
        "https:///missing-host",
    ],
)
def test_rejects_unsafe_urls(url: str) -> None:
    _assert_rejected("invalid_url", url=url)


def test_canonicalize_document_url_returns_url_and_domain() -> None:
    canonical_url, source_domain = canonicalize_document_url("https://EXAMPLE.com/Path")
    assert canonical_url == "https://example.com/Path"
    assert source_domain == "example.com"


@pytest.mark.parametrize("title", ["", "   "])
def test_rejects_empty_title(title: str) -> None:
    _assert_rejected("invalid_title", title=title)


def test_strips_title_and_rejects_overlong_title() -> None:
    assert _admit(title="  Valid title  ").title == "Valid title"
    _assert_rejected("invalid_title", title="x" * 501)


@pytest.mark.parametrize("fetched_at", ["2026-06-24T12:00:00", "not-a-time", "2026-99-24T12:00:00Z"])
def test_rejects_invalid_or_naive_timestamps(fetched_at: str) -> None:
    _assert_rejected("invalid_fetched_at", fetched_at=fetched_at)


def test_normalizes_fetched_at_to_utc_iso() -> None:
    assert _admit(fetched_at="2026-06-24T12:00:00+08:00").fetched_at == "2026-06-24T04:00:00+00:00"
    assert _admit(fetched_at="2026-06-24T04:00:00Z").fetched_at == "2026-06-24T04:00:00+00:00"


@pytest.mark.parametrize("raw_text", ["", "   ", "abc\x00def"])
def test_rejects_invalid_raw_text(raw_text: str) -> None:
    _assert_rejected("invalid_raw_text", raw_text=raw_text)


def test_rejects_raw_text_larger_than_one_mib() -> None:
    _assert_rejected("raw_text_too_large", raw_text="x" * (1024 * 1024 + 1))


@pytest.mark.parametrize(
    "marker",
    [
        "TAVILY_API_KEY",
        "DEEPSEEK_API_KEY",
        "FRED_API_KEY",
        "BLS_API_KEY",
        ".env",
        "data/holdings/",
        "data/private/",
        "data/private_notes/",
        "current_holdings.csv",
        "sk-1234567890abcdef",
        r"C:\Users\alice\secret.txt",
        "C:/Users/alice/secret.txt",
        "/home/alice/secret.txt",
        "/Users/alice/secret.txt",
    ],
)
def test_rejects_sensitive_raw_text_markers(marker: str) -> None:
    _assert_rejected("sensitive_content_rejected", raw_text=f"public text {marker}")


@pytest.mark.parametrize("word", ["account", "position", "holding", "portfolio holdings debate"])
def test_does_not_reject_generic_finance_words(word: str) -> None:
    assert _admit(raw_text=f"Public macro article about {word}.").content_sha256


def test_content_hash_uses_original_utf8_raw_text() -> None:
    raw_text = "  macro text with accents café  "
    assert _admit(raw_text=raw_text).content_sha256 == sha256(raw_text.encode("utf-8")).hexdigest()


def test_output_is_metadata_plus_process_local_raw_text_only() -> None:
    admitted = _admit()
    names = {field.name for field in fields(admitted)}
    assert names == {
        "canonical_url",
        "title",
        "source_domain",
        "doc_type",
        "fetched_at",
        "raw_text",
        "content_sha256",
    }
    assert "db_path" not in names
    assert "raw_text_path" not in names
    assert "chunk_text" not in names
    assert "embedding_vector_id" not in names


def test_input_does_not_accept_caller_controlled_storage_or_provider_fields() -> None:
    names = {field.name for field in fields(KnowledgeDocumentInput)}
    assert names == {"url", "title", "doc_type", "fetched_at", "raw_text"}
    with pytest.raises(TypeError):
        KnowledgeDocumentInput(
            url="https://example.com",
            title="Title",
            doc_type="policy_doc",
            fetched_at="2026-06-24T00:00:00+00:00",
            raw_text="text",
            source_domain="evil.example",  # type: ignore[call-arg]
        )


def test_dataclasses_are_frozen() -> None:
    document = _input()
    admitted = _admit()
    with pytest.raises(FrozenInstanceError):
        document.title = "Changed"
    with pytest.raises(FrozenInstanceError):
        admitted.title = "Changed"


def test_admission_error_does_not_echo_raw_inputs() -> None:
    secret_url = "https://user:secret@example.com/report"
    with pytest.raises(KnowledgeBaseAdmissionError) as exc_info:
        _admit(url=secret_url, raw_text="raw sk-1234567890abcdef")
    serialized = str(exc_info.value)
    assert serialized == "invalid_url"
    assert secret_url not in serialized
    assert "sk-" not in serialized


def test_contract_source_has_no_forbidden_imports_or_runtime_boundaries() -> None:
    source = CONTRACT_SOURCE.read_text(encoding="utf-8")
    forbidden = [
        "pathlib",
        "sqlite3",
        "httpx",
        "requests",
        "aiohttp",
        "os.getenv",
        "os.environ",
        "FastAPI",
        "main.py",
        "data_providers",
        "app_backend.services.",
    ]
    assert not any(token in source for token in forbidden)


def test_schema_defines_required_tables_migration_and_foreign_keys() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in schema
    assert "INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)" in schema
    assert "CREATE TABLE IF NOT EXISTS documents" in schema
    assert "CREATE TABLE IF NOT EXISTS document_chunks" in schema
    assert "FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE" in schema
    assert "UNIQUE (doc_id, chunk_index)" in schema


def test_schema_documents_table_has_required_metadata_columns_and_constraints() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    for column in [
        "id INTEGER PRIMARY KEY",
        "url TEXT NOT NULL UNIQUE",
        "title TEXT NOT NULL",
        "source_domain TEXT NOT NULL",
        "doc_type TEXT NOT NULL CHECK",
        "fetched_at TEXT NOT NULL",
        "content_sha256 TEXT NOT NULL",
        "raw_text_path TEXT NOT NULL",
        "is_stale INTEGER NOT NULL DEFAULT 0 CHECK (is_stale IN (0, 1))",
        "stale_at TEXT",
        "created_at TEXT NOT NULL",
        "updated_at TEXT NOT NULL",
    ]:
        assert column in schema
    for doc_type in [item.value for item in KnowledgeDocumentType]:
        assert doc_type in schema


def test_schema_has_required_indexes() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "idx_documents_url ON documents(url)" in schema
    assert "idx_documents_fetched_at ON documents(fetched_at DESC)" in schema
    assert "idx_documents_stale_fetched_at ON documents(is_stale, fetched_at DESC)" in schema
    assert "idx_document_chunks_doc_index ON document_chunks(doc_id, chunk_index)" in schema


def test_schema_documents_table_does_not_store_raw_text_or_sensitive_columns() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    documents_body = re.search(
        r"CREATE TABLE IF NOT EXISTS documents \((.*?)\);\n\nCREATE TABLE",
        schema,
        re.DOTALL,
    )
    assert documents_body is not None
    body = documents_body.group(1).lower()
    forbidden = ["raw_text ", "provider_payload", "api_key", "account", "holdings", "embedding_vector"]
    assert not any(token in body for token in forbidden)
