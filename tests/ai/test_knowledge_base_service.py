from __future__ import annotations

from dataclasses import fields, is_dataclass
from hashlib import sha256
import inspect
from pathlib import Path
import sqlite3

import pytest

from app_backend.services.knowledge_base_contracts import (
    KnowledgeBaseAdmissionError,
    KnowledgeDocumentInput,
)
from app_backend.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeDocumentRecord,
    KnowledgeIngestResult,
    KnowledgeMutationResult,
    build_default_knowledge_base_service,
)


SERVICE_SOURCE = (
    Path(__file__).parents[2]
    / "src"
    / "app_backend"
    / "services"
    / "knowledge_base_service.py"
)


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "knowledge_base.sqlite", tmp_path / "knowledge_base" / "raw"


def _service(tmp_path: Path) -> KnowledgeBaseService:
    db_path, raw_root = _paths(tmp_path)
    return KnowledgeBaseService(db_path=db_path, raw_root=raw_root)


def _document(**overrides: str) -> KnowledgeDocumentInput:
    values = {
        "url": "https://Example.com/policy/report",
        "title": "Macro policy report",
        "doc_type": "policy_doc",
        "fetched_at": "2026-06-24T08:00:00+00:00",
        "raw_text": "Public macro source text.",
    }
    values.update(overrides)
    return KnowledgeDocumentInput(**values)


def _ingest(tmp_path: Path, **overrides: str) -> KnowledgeIngestResult:
    return _service(tmp_path).ingest_document(_document(**overrides))


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def test_import_and_default_factory_create_no_tmp_files(tmp_path: Path) -> None:
    db_path, raw_root = _paths(tmp_path)
    service = KnowledgeBaseService(db_path=db_path, raw_root=raw_root)
    default_service = build_default_knowledge_base_service()
    assert isinstance(service, KnowledgeBaseService)
    assert isinstance(default_service, KnowledgeBaseService)
    assert not db_path.exists()
    assert not raw_root.exists()


def test_lookup_list_and_mark_stale_missing_db_create_no_files(tmp_path: Path) -> None:
    db_path, raw_root = _paths(tmp_path)
    service = _service(tmp_path)
    assert service.lookup_by_url("https://example.com/policy/report") is None
    assert service.list_recent() == []
    assert service.mark_stale("https://example.com/policy/report").status == "not_found"
    assert not db_path.exists()
    assert not raw_root.exists()


@pytest.mark.parametrize("doc_type", ["policy_doc", "research_report", "historical_data", "one_shot_news"])
def test_ingests_each_supported_document_type(tmp_path: Path, doc_type: str) -> None:
    result = _ingest(tmp_path, doc_type=doc_type, url=f"https://example.com/{doc_type}")
    assert result.status == "created"
    assert result.created is True
    assert result.updated is False
    assert result.document.doc_type == doc_type


def test_ingest_creates_schema_version_and_tables(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection:
        version = connection.execute("SELECT version FROM schema_migrations").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert version == 1
    assert {"schema_migrations", "documents", "document_chunks"} <= tables


def test_documents_table_has_no_raw_text_column_and_chunks_start_empty(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
        chunk_count = connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    assert "raw_text" not in columns
    assert "provider_payload" not in columns
    assert chunk_count == 0


def test_ingest_stores_metadata_hash_and_relative_raw_path(tmp_path: Path) -> None:
    db_path, raw_root = _paths(tmp_path)
    raw_text = "Macro text for hashing."
    result = _ingest(tmp_path, raw_text=raw_text)
    expected_hash = sha256(raw_text.encode("utf-8")).hexdigest()
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT url, source_domain, content_sha256, raw_text_path FROM documents"
        ).fetchone()
    assert row == ("https://example.com/policy/report", "example.com", expected_hash, f"raw/{expected_hash}.txt")
    raw_file = raw_root / f"{expected_hash}.txt"
    assert raw_file.exists()
    assert sha256(raw_file.read_bytes()).hexdigest() == result.document.content_sha256


def test_ingest_creates_only_configured_db_and_raw_root(tmp_path: Path) -> None:
    db_path, raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    assert db_path.exists()
    assert raw_root.exists()
    assert sorted(path.name for path in raw_root.parent.iterdir()) == ["raw"]


def test_source_domain_is_derived_from_canonical_url_not_input(tmp_path: Path) -> None:
    result = _ingest(tmp_path, url="https://WWW.Example.ORG/report")
    assert result.document.url == "https://www.example.org/report"
    assert result.document.source_domain == "www.example.org"


def test_raw_file_is_not_duplicated_for_same_url_same_content(tmp_path: Path) -> None:
    _ingest(tmp_path)
    _ingest(tmp_path, title="Metadata change only")
    _db_path, raw_root = _paths(tmp_path)
    assert len(list(raw_root.glob("*.txt"))) == 1


def test_changed_content_keeps_old_raw_file_without_garbage_collection(tmp_path: Path) -> None:
    _ingest(tmp_path, raw_text="First public text.")
    _ingest(tmp_path, raw_text="Second public text.")
    _db_path, raw_root = _paths(tmp_path)
    assert len(list(raw_root.glob("*.txt"))) == 2


def test_public_ingest_result_and_record_do_not_expose_storage_or_text(tmp_path: Path) -> None:
    result = _ingest(tmp_path)
    serialized = repr(result)
    assert "Public macro source text" not in serialized
    assert "raw/" not in serialized
    assert "knowledge_base.sqlite" not in serialized
    record_fields = {field.name for field in fields(KnowledgeDocumentRecord)}
    result_fields = {field.name for field in fields(KnowledgeIngestResult)}
    assert "raw_text" not in record_fields
    assert "raw_text_path" not in record_fields
    assert "chunk_text" not in record_fields
    assert "embedding_vector_id" not in record_fields
    assert "db_path" not in record_fields | result_fields


def test_same_url_same_text_updates_existing_document_without_duplicate(tmp_path: Path) -> None:
    first = _ingest(tmp_path)
    second = _ingest(tmp_path, title="Updated title")
    db_path, _raw_root = _paths(tmp_path)
    with _connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert first.document.id == second.document.id
    assert second.status == "updated"
    assert second.document.title == "Updated title"
    assert count == 1


def test_same_url_new_text_keeps_id_updates_hash_and_clears_stale(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.ingest_document(_document())
    assert service.mark_stale(first.document.url).status == "stale"
    second = service.ingest_document(_document(raw_text="Changed public macro text."))
    assert second.document.id == first.document.id
    assert second.document.content_sha256 != first.document.content_sha256
    assert second.document.is_stale is False
    assert second.document.stale_at is None


def test_same_url_same_text_reingest_clears_stale(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inserted = service.ingest_document(_document())
    service.mark_stale(inserted.document.url)
    reingested = service.ingest_document(_document())
    assert reingested.document.id == inserted.document.id
    assert reingested.document.is_stale is False
    assert reingested.document.stale_at is None


def test_content_update_deletes_existing_chunks(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    first = _ingest(tmp_path)
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO document_chunks (doc_id, chunk_index, text, embedding_vector_id) VALUES (?, 0, ?, NULL)",
            (first.document.id, "test-only chunk"),
        )
    _ingest(tmp_path, raw_text="Changed text clears chunks.")
    with _connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    assert count == 0


def test_different_urls_same_text_share_one_raw_file_but_two_documents(tmp_path: Path) -> None:
    raw_text = "Shared public macro text."
    first = _ingest(tmp_path, url="https://example.com/a", raw_text=raw_text)
    second = _ingest(tmp_path, url="https://example.com/b", raw_text=raw_text)
    db_path, raw_root = _paths(tmp_path)
    with _connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert first.document.id != second.document.id
    assert count == 2
    assert len(list(raw_root.glob("*.txt"))) == 1


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"doc_type": "discard"}, "unsupported_doc_type"),
        ({"title": ""}, "invalid_title"),
        ({"fetched_at": "2026-06-24T00:00:00"}, "invalid_fetched_at"),
        ({"raw_text": "\x00"}, "invalid_raw_text"),
        ({"url": "http://example.com"}, "invalid_url"),
        ({"url": "https://127.0.0.1/report"}, "invalid_url"),
        ({"url": "https://example.com/report?x=1"}, "invalid_url"),
        ({"raw_text": "TAVILY_API_KEY"}, "sensitive_content_rejected"),
        ({"raw_text": "x" * (1024 * 1024 + 1)}, "raw_text_too_large"),
    ],
)
def test_invalid_ingest_rejects_without_creating_db_or_raw_file(
    tmp_path: Path,
    overrides: dict[str, str],
    code: str,
) -> None:
    db_path, raw_root = _paths(tmp_path)
    with pytest.raises(KnowledgeBaseAdmissionError) as exc_info:
        _ingest(tmp_path, **overrides)
    assert exc_info.value.code == code
    assert not db_path.exists()
    assert not raw_root.exists()


def test_lookup_returns_metadata_only_and_canonicalizes_url(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inserted = service.ingest_document(_document())
    found = service.lookup_by_url("https://EXAMPLE.com/policy/report")
    assert found == inserted.document
    assert "raw" not in repr(found)
    assert "Public macro source text" not in repr(found)


def test_lookup_missing_url_with_existing_db_returns_none(tmp_path: Path) -> None:
    _ingest(tmp_path)
    assert _service(tmp_path).lookup_by_url("https://example.com/missing") is None


def test_lookup_invalid_url_raises_stable_error_without_echo(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseAdmissionError) as exc_info:
        _service(tmp_path).lookup_by_url("https://user:secret@example.com/report")
    assert exc_info.value.code == "invalid_url"
    assert "secret" not in str(exc_info.value)


def test_mark_stale_invalid_url_raises_stable_error_without_echo(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseAdmissionError) as exc_info:
        _service(tmp_path).mark_stale("https://user:secret@example.com/report")
    assert exc_info.value.code == "invalid_url"
    assert "secret" not in str(exc_info.value)


def test_mark_stale_sets_metadata_only_and_is_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inserted = service.ingest_document(_document())
    first = service.mark_stale(inserted.document.url)
    second = service.mark_stale(inserted.document.url)
    assert first.status == "stale"
    assert second.status == "stale"
    assert second.document is not None
    assert second.document.is_stale is True
    assert second.document.stale_at is not None


def test_mutation_result_does_not_expose_storage_or_text(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inserted = service.ingest_document(_document())
    result = service.mark_stale(inserted.document.url)
    serialized = repr(result)
    assert "raw/" not in serialized
    assert "knowledge_base.sqlite" not in serialized
    assert "Public macro source text" not in serialized


def test_mark_stale_missing_url_returns_not_found(tmp_path: Path) -> None:
    _ingest(tmp_path)
    result = _service(tmp_path).mark_stale("https://example.com/missing")
    assert result.status == "not_found"
    assert result.document is None


def test_stale_documents_are_hidden_by_default_and_visible_when_requested(tmp_path: Path) -> None:
    service = _service(tmp_path)
    inserted = service.ingest_document(_document())
    service.mark_stale(inserted.document.url)
    assert service.list_recent() == []
    assert [item.id for item in service.list_recent(include_stale=True)] == [inserted.document.id]


def test_list_recent_orders_by_fetched_at_desc_then_id_desc(tmp_path: Path) -> None:
    service = _service(tmp_path)
    older = service.ingest_document(
        _document(url="https://example.com/older", fetched_at="2026-06-23T00:00:00+00:00")
    )
    same_time_first = service.ingest_document(
        _document(url="https://example.com/a", fetched_at="2026-06-24T00:00:00+00:00")
    )
    same_time_second = service.ingest_document(
        _document(url="https://example.com/b", fetched_at="2026-06-24T00:00:00+00:00")
    )
    assert [item.id for item in service.list_recent(limit=3)] == [
        same_time_second.document.id,
        same_time_first.document.id,
        older.document.id,
    ]


def test_list_recent_limit_caps_results(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.ingest_document(_document(url="https://example.com/one"))
    service.ingest_document(_document(url="https://example.com/two"))
    assert len(service.list_recent(limit=1)) == 1


@pytest.mark.parametrize("limit", [0, -1, 101, 1.5, True, "2", None, {}])
def test_list_recent_rejects_invalid_limits(tmp_path: Path, limit) -> None:
    with pytest.raises(KnowledgeBaseAdmissionError) as exc_info:
        _service(tmp_path).list_recent(limit=limit)
    assert exc_info.value.code == "invalid_limit"


def test_unique_url_constraint_is_enforced(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO documents (
                url, title, source_domain, doc_type, fetched_at, content_sha256,
                raw_text_path, is_stale, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                "https://example.com/policy/report",
                "Title",
                "example.com",
                "policy_doc",
                "2026-06-24T00:00:00+00:00",
                "a" * 64,
                "raw/test.txt",
                "2026-06-24T00:00:00+00:00",
                "2026-06-24T00:00:00+00:00",
            ),
        )


def test_foreign_key_constraint_is_enforced(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO document_chunks (doc_id, chunk_index, text, embedding_vector_id) VALUES (999, 0, ?, NULL)",
            ("orphan",),
        )


def test_document_chunks_unique_doc_index_constraint_is_enforced(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    inserted = _ingest(tmp_path)
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO document_chunks (doc_id, chunk_index, text, embedding_vector_id) VALUES (?, 0, ?, NULL)",
            (inserted.document.id, "first"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO document_chunks (doc_id, chunk_index, text, embedding_vector_id) VALUES (?, 0, ?, NULL)",
                (inserted.document.id, "second"),
            )


def test_document_chunks_embedding_vector_id_remains_null_after_ingest(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection:
        values = connection.execute("SELECT embedding_vector_id FROM document_chunks").fetchall()
    assert values == []


def test_schema_rejects_invalid_doc_type_direct_write(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO documents (
                url, title, source_domain, doc_type, fetched_at, content_sha256,
                raw_text_path, is_stale, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                "https://example.com/bad-type",
                "Title",
                "example.com",
                "discard",
                "2026-06-24T00:00:00+00:00",
                "b" * 64,
                "raw/test.txt",
                "2026-06-24T00:00:00+00:00",
                "2026-06-24T00:00:00+00:00",
            ),
        )


def test_schema_rejects_invalid_is_stale_direct_write(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE documents SET is_stale = 2")


def test_schema_rejects_short_content_hash_direct_write(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    _ingest(tmp_path)
    with _connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE documents SET content_sha256 = 'short'")


def test_raw_relative_path_is_hash_derived_not_input_driven(tmp_path: Path) -> None:
    db_path, _raw_root = _paths(tmp_path)
    result = _ingest(tmp_path, url="https://example.com/a/../reject".replace("/../", "/safe/"))
    with _connect(db_path) as connection:
        raw_path = connection.execute("SELECT raw_text_path FROM documents").fetchone()[0]
    assert raw_path == f"raw/{result.document.content_sha256}.txt"
    assert ".." not in raw_path
    assert not Path(raw_path).is_absolute()


def test_public_methods_are_strictly_limited() -> None:
    methods = {
        name
        for name, value in inspect.getmembers(KnowledgeBaseService, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {"ingest_document", "lookup_by_url", "mark_stale", "list_recent"}


def test_service_source_has_no_forbidden_runtime_boundaries() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    forbidden = [
        "httpx",
        "requests",
        "aiohttp",
        "os.environ",
        "os.getenv",
        "FastAPI",
        "main.py",
        "Tavily",
        "DeepSeek",
        "data_providers",
        "fetch_url",
        "download",
        "crawl",
        "seed",
        "vector_query",
    ]
    assert not any(token in source for token in forbidden)


def test_only_service_source_imports_sqlite3_for_knowledge_base() -> None:
    assert "import sqlite3" in SERVICE_SOURCE.read_text(encoding="utf-8")


def test_public_result_dataclasses_expose_metadata_only() -> None:
    for klass in [KnowledgeDocumentRecord, KnowledgeIngestResult, KnowledgeMutationResult]:
        assert is_dataclass(klass)
    forbidden_fields = {
        "raw_text",
        "raw_text_path",
        "chunk_text",
        "embedding_vector_id",
        "db_path",
        "sqlite_path",
    }
    for klass in [KnowledgeDocumentRecord, KnowledgeIngestResult, KnowledgeMutationResult]:
        assert not ({field.name for field in fields(klass)} & forbidden_fields)
