from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from app_backend.services.curated_rag_ingest import build_ingest_plan, ingest_curated_corpus
from app_backend.services.rag_index_generation import (
    CHUNKING_VERSION,
    INDEX_GENERATION_SCHEMA_VERSION,
    write_index_generation_metadata,
)
from llm.chunk_text_store import ChunkTextStore, StoredChunk


class _FakeEmbedding:
    model_name = "fake-bge"
    dim = 2

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


class _FakeVectorStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, int, dict[str, object]]] = []
        self.items: dict[tuple[str, int], tuple[list[float], dict[str, object]]] = {}
        self.deleted: list[str] = []

    def delete(self, doc_id: str) -> int:
        self.deleted.append(doc_id)
        self.upserts = [item for item in self.upserts if item[0] != doc_id]
        deleted = 0
        for key in list(self.items):
            if key[0] == doc_id:
                deleted += 1
                del self.items[key]
        return deleted

    def upsert(self, doc_id: str, chunk_index: int, embedding: list[float], metadata: dict[str, object]) -> None:
        self.upserts.append((doc_id, chunk_index, metadata))
        self.items[(doc_id, chunk_index)] = (embedding, metadata)

    def upsert_many(self, items: list[tuple[str, int, list[float], dict[str, object]]]) -> None:
        for doc_id, chunk_index, embedding, metadata in items:
            self.upsert(doc_id, chunk_index, embedding, metadata)

    def list_doc_items(self, doc_id: str) -> list[object]:
        return [
            types.SimpleNamespace(
                doc_id=item_doc_id,
                chunk_index=chunk_index,
                embedding=embedding,
                metadata=metadata,
            )
            for (item_doc_id, chunk_index), (embedding, metadata) in sorted(self.items.items())
            if item_doc_id == doc_id
        ]

    def count(self) -> int:
        return len(self.items)


class _FailingVectorStore(_FakeVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_upsert = False

    def upsert(self, doc_id: str, chunk_index: int, embedding: list[float], metadata: dict[str, object]) -> None:
        if self.fail_next_upsert:
            self.fail_next_upsert = False
            raise RuntimeError("vector write failed")
        super().upsert(doc_id, chunk_index, embedding, metadata)


def _write_doc(root: Path, relpath: str, text: str) -> str:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _base_row(root: Path, *, document_id: str = "fomc_statement_2026_06_17") -> dict[str, object]:
    relpath = "policy_doc/fomc_statement_2026_06_17.md"
    digest = _write_doc(root, relpath, "# FOMC Statement - 2026-06-17\n\nFederal funds target range.")
    return {
        "document_id": document_id,
        "output_relpath": relpath,
        "cohort": "policy_doc",
        "extraction_status": "ready",
        "provenance_status": "verified",
        "ingest_status": "eligible",
        "external_llm_context_allowed": True,
        "allowed_use": "external_context_candidate",
        "runtime_doc_type": "policy_doc",
        "evidence_tier": "official_evidence",
        "is_official_source": True,
        "canonical_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
        "source_domain": "www.federalreserve.gov",
        "cleaned_content_sha256": digest,
        "source_relpath": "FOMC/statement/monetary20260617a1.pdf",
        "source_file_sha256": "f" * 64,
        "source_kind": "central_bank_policy",
        "temporal_status": "as_released",
        "release_date": "2026-06-17",
        "fomc_material_type": "statement",
    }


def _manifest(root: Path, rows: list[dict[str, object]], name: str = "rag_manifest.jsonl") -> Path:
    metadata = root / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    path = metadata / name
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows), encoding="utf-8")
    return path


def _write_generation(
    vector_root: Path,
    *,
    embedding_model: str = "fake-bge",
    embedding_dim: int = 2,
    chunking_version: str = CHUNKING_VERSION,
    vector_enabled: bool = True,
) -> None:
    write_index_generation_metadata(
        vector_root,
        {
            "schema_version": INDEX_GENERATION_SCHEMA_VERSION,
            "generation_id": "existing-generation",
            "chunking_version": chunking_version,
            "vector_enabled": vector_enabled,
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dim,
        },
    )


def _seed_existing_index(
    vector_root: Path,
    vector_store: _FakeVectorStore,
    *,
    generation: dict[str, object] | None = None,
) -> ChunkTextStore:
    chunk_store = ChunkTextStore(vector_root / "chunks.sqlite")
    chunk_store.upsert_chunk(
        StoredChunk(
            doc_id="fomc_statement_2026_06_17",
            chunk_index=0,
            text="old active chunk",
            title="Old active",
            doc_type="policy_doc",
            source_domain="www.federalreserve.gov",
            external_llm_context_allowed=True,
            evidence_tier="official_evidence",
            is_official_source=True,
        )
    )
    vector_store.upsert(
        "fomc_statement_2026_06_17",
        0,
        [1.0, 0.0],
        {"doc_id": "fomc_statement_2026_06_17", "chunk_index": 0, "doc_type": "policy_doc"},
    )
    if generation is not None:
        _write_generation(vector_root, **generation)
    return chunk_store


def _assert_existing_index_unchanged(chunk_store: ChunkTextStore, vector_store: _FakeVectorStore) -> None:
    active = chunk_store.get_chunk("fomc_statement_2026_06_17", 0)
    assert active is not None
    assert active.text == "old active chunk"
    assert vector_store.deleted == []
    assert vector_store.upserts == [
        (
            "fomc_statement_2026_06_17",
            0,
            {"doc_id": "fomc_statement_2026_06_17", "chunk_index": 0, "doc_type": "policy_doc"},
        )
    ]


def test_eligible_manifest_document_can_be_planned(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row], name="derived_manifest.jsonl")

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1
    assert plan.doc_type_counts == {"policy_doc": 1}
    assert plan.fomc_material_type_counts == {"statement": 1}


def test_hold_local_only_pending_and_review_required_are_not_seeded(tmp_path):
    rows = []
    for cohort, ingest_status in [
        ("pending_governance", "hold"),
        ("review_required", "eligible"),
        ("local_only", "local_only"),
    ]:
        row = _base_row(tmp_path, document_id=f"doc_{cohort}")
        row["cohort"] = cohort
        row["ingest_status"] = ingest_status
        row["output_relpath"] = f"{cohort}/doc.md"
        row["cleaned_content_sha256"] = _write_doc(tmp_path, f"{cohort}/doc.md", "# Doc\n\nBody")
        if cohort == "local_only":
            row["external_llm_context_allowed"] = False
            row["allowed_use"] = "local_search_only"
        rows.append(row)
    manifest = _manifest(tmp_path, rows)

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.skipped_reasons["cohort_pending_governance"] == 1
    assert plan.skipped_reasons["cohort_review_required"] == 1
    assert plan.skipped_reasons["cohort_local_only"] == 1


def test_invalid_runtime_doc_type_is_rejected(tmp_path):
    row = _base_row(tmp_path)
    row["runtime_doc_type"] = "historical_data"
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["invalid_runtime_doc_type"] == 1


def test_cleaned_content_hash_mismatch_is_rejected(tmp_path):
    row = _base_row(tmp_path)
    row["cleaned_content_sha256"] = "0" * 64
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["cleaned_content_hash_mismatch"] == 1


def test_cleaned_content_hash_uses_normalized_line_endings(tmp_path):
    text_lf = "# FOMC Statement - 2026-06-17\n\nFederal funds target range.\n"
    text_crlf = text_lf.replace("\n", "\r\n")
    relpath = "policy_doc/fomc_statement_2026_06_17.md"
    row = _base_row(tmp_path)
    path = tmp_path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_crlf, encoding="utf-8", newline="")
    row["output_relpath"] = relpath
    row["cleaned_content_sha256"] = hashlib.sha256(text_lf.encode("utf-8")).hexdigest()
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1


def test_canonical_url_source_domain_mismatch_is_rejected(tmp_path):
    row = _base_row(tmp_path)
    row["source_domain"] = "example.com"
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["canonical_url_source_domain_mismatch"] == 1


def test_missing_canonical_url_is_rejected(tmp_path):
    row = _base_row(tmp_path)
    row["canonical_url"] = None
    row["source_relpath"] = ""
    row["source_file_sha256"] = ""
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["missing_canonical_url"] == 1


def test_verified_local_provenance_can_be_planned_without_canonical_url(tmp_path):
    row = _base_row(tmp_path)
    row["canonical_url"] = None
    row["source_domain"] = None
    row["admission_source"] = "source_ledger"
    row["admission_status"] = "verified"
    row["admission_reason"] = "verified_fomc_policy_doc"
    row["verified_by"] = "user"
    row["verification_basis"] = "user_curated_local_file"
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1
    assert plan.accepted[0].source_domain == "local_user_verified"


def test_official_release_manifest_document_can_be_planned(tmp_path):
    relpath = "official_release/bls_cpi_2026_05.md"
    digest = _write_doc(
        tmp_path,
        relpath,
        "# BLS Consumer Price Index - 2026-05\n\n## Narrative Layer\n\nCPI rose in May.\n\n## Table Layer\n\n```text\nTable A 0.5 2.1 3.4 4.0\n```\n",
    )
    row = {
        "document_id": "bls_cpi_2026_05",
        "output_relpath": relpath,
        "cohort": "official_release",
        "extraction_status": "ready",
        "provenance_status": "verified",
        "ingest_status": "eligible",
        "external_llm_context_allowed": True,
        "allowed_use": "external_context_candidate",
        "runtime_doc_type": "official_release",
        "evidence_tier": "official_evidence",
        "is_official_source": True,
        "canonical_url": None,
        "source_domain": None,
        "source_relpath": "BLS/cpi.pdf",
        "source_file_sha256": "f" * 64,
        "cleaned_content_sha256": digest,
        "source_kind": "official_release",
        "release_date": "2026-06-10",
        "observation_period": "2026-05",
        "material_type": "cpi_release",
        "factual_status": "historical_release",
        "vintage": "as_released",
        "table_quality": "review_required",
        "content_layers": ["narrative", "table"],
    }
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1
    assert plan.doc_type_counts == {"official_release": 1}
    assert plan.accepted[0].metadata["observation_period"] == "2026-05"
    assert plan.accepted[0].metadata["content_layers"] == "narrative,table"


def test_authorized_institutional_view_can_be_planned(tmp_path):
    relpath = "research_report/memo.md"
    digest = _write_doc(tmp_path, relpath, "# Institutional Memo\n\nA bank research view.")
    row = {
        "document_id": "research_report_macro_view",
        "output_relpath": relpath,
        "cohort": "research_report",
        "extraction_status": "ready",
        "provenance_status": "verified",
        "ingest_status": "eligible",
        "external_llm_context_allowed": True,
        "allowed_use": "external_context_candidate",
        "runtime_doc_type": "research_report",
        "candidate_doc_type": "research_report",
        "canonical_url": None,
        "source_domain": None,
        "source_relpath": "MEMO/memo.pdf",
        "source_file_sha256": "a" * 64,
        "cleaned_content_sha256": digest,
        "source_kind": "institutional_research",
        "evidence_tier": "institutional_view",
        "is_official_source": False,
        "rights_status": "user_authorized_external_context",
    }
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1
    assert plan.accepted[0].metadata["evidence_tier"] == "institutional_view"
    assert plan.accepted[0].metadata["is_official_source"] is False


def test_institutional_research_cannot_be_marked_official(tmp_path):
    relpath = "research_report/memo.md"
    digest = _write_doc(tmp_path, relpath, "# Institutional Memo\n\nA bank research view.")
    row = {
        "document_id": "research_report_macro_view",
        "output_relpath": relpath,
        "cohort": "research_report",
        "extraction_status": "ready",
        "provenance_status": "verified",
        "ingest_status": "eligible",
        "external_llm_context_allowed": True,
        "allowed_use": "external_context_candidate",
        "runtime_doc_type": "research_report",
        "canonical_url": None,
        "source_domain": None,
        "source_relpath": "MEMO/memo.pdf",
        "source_file_sha256": "a" * 64,
        "cleaned_content_sha256": digest,
        "source_kind": "institutional_research",
        "evidence_tier": "official_evidence",
        "is_official_source": True,
    }
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["institutional_research_not_view_tier"] == 1


def test_manifest_verified_provenance_with_source_markers_is_admitted(tmp_path):
    row = _base_row(tmp_path)
    row["canonical_url"] = None
    row["source_domain"] = None
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1
    assert plan.accepted[0].source_domain == "local_user_verified"


def test_unverified_provenance_without_admission_markers_is_rejected(tmp_path):
    row = _base_row(tmp_path)
    row["canonical_url"] = None
    row["source_domain"] = None
    row["provenance_status"] = "pending"
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.skipped_reasons["provenance_pending"] == 1


def test_missing_source_file_markers_blocks_local_admission(tmp_path):
    row = _base_row(tmp_path)
    row["canonical_url"] = None
    row["source_domain"] = None
    row["source_file_sha256"] = ""
    manifest = _manifest(tmp_path, [row])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["missing_canonical_url"] == 1


def test_duplicate_document_id_is_rejected(tmp_path):
    first = _base_row(tmp_path)
    second = _base_row(tmp_path, document_id=first["document_id"])
    second["output_relpath"] = "research_report/other.md"
    second["runtime_doc_type"] = "research_report"
    second["cohort"] = "research_report"
    second["cleaned_content_sha256"] = _write_doc(tmp_path, "research_report/other.md", "# Other\n\nBody")
    manifest = _manifest(tmp_path, [first, second])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["duplicate_document_id"] == 2


def test_identical_cross_cohort_copies_collapse_to_priority_cohort(tmp_path):
    primary = _base_row(tmp_path)
    review_relpath = "review_required/fomc_statement_2026_06_17.md"
    review_text = (tmp_path / primary["output_relpath"]).read_text(encoding="utf-8")
    digest = _write_doc(tmp_path, review_relpath, review_text)
    review = dict(primary)
    review["cohort"] = "review_required"
    review["output_relpath"] = review_relpath
    review["cleaned_content_sha256"] = digest
    manifest = _manifest(tmp_path, [review, primary])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 1
    assert plan.accepted[0].path.name == "fomc_statement_2026_06_17.md"
    assert "policy_doc" in str(plan.accepted[0].path)
    assert plan.skipped_reasons["duplicate_cohort_copy"] == 1


def test_same_id_different_content_still_rejects_as_duplicate(tmp_path):
    first = _base_row(tmp_path)
    second_relpath = "policy_doc/other.md"
    second_hash = _write_doc(tmp_path, second_relpath, "# Different\n\nBody")
    second = dict(first)
    second["output_relpath"] = second_relpath
    second["cleaned_content_sha256"] = second_hash
    manifest = _manifest(tmp_path, [first, second])

    plan = build_ingest_plan(tmp_path, manifest)

    assert plan.accepted_document_count == 0
    assert plan.rejected_reasons["duplicate_document_id"] == 2


def test_dry_run_does_not_write_chunk_store_or_vector_store(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector = _FakeVectorStore()
    chunk_store = ChunkTextStore(tmp_path / "vector_store" / "chunks.sqlite")

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_dir=tmp_path / "vector_store",
        write=False,
        embedding_service=_FakeEmbedding(),
        vector_store=vector,
        chunk_store=chunk_store,
    )

    assert result.mode == "dry-run"
    assert result.written_chunk_count == 0
    assert not (tmp_path / "vector_store" / "chunks.sqlite").exists()
    assert vector.upserts == []


def test_write_with_zero_eligible_documents_does_not_create_vector_root(tmp_path):
    row = _base_row(tmp_path)
    row["canonical_url"] = None
    row["source_relpath"] = ""
    row["source_file_sha256"] = ""
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_root=vector_root,
        write=True,
        embedding_service=_FakeEmbedding(),
        vector_store=_FakeVectorStore(),
        chunk_store=ChunkTextStore(vector_root / "chunks.sqlite"),
    )

    assert result.mode == "blocked-no-eligible"
    assert result.written_chunk_count == 0
    assert not (vector_root / "chunks.sqlite").exists()
    assert not (vector_root / "ingest_audits").exists()


def test_write_missing_offline_embedding_model_writes_bm25_only_chunks(tmp_path, monkeypatch):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str, *, local_files_only: bool = False) -> None:
            raise OSError("not cached")

    fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_root=vector_root,
        write=True,
        offline_only=True,
    )

    assert result.mode == "write-bm25-only"
    assert result.written_chunk_count > 0
    stored = ChunkTextStore(vector_root / "chunks.sqlite")
    assert stored.list_doc_ids() == ["fomc_statement_2026_06_17"]
    first_chunk = stored.get_chunk("fomc_statement_2026_06_17", 0)
    assert first_chunk is not None
    assert first_chunk.release_date == "2026-06-17"
    assert not (vector_root / "chroma").exists()
    assert (vector_root / "ingest_audits" / "last_ingest_audit.json").exists()


def test_strict_write_blocks_when_any_manifest_record_is_rejected(tmp_path):
    good = _base_row(tmp_path)
    bad = _base_row(tmp_path, document_id="bad_doc")
    bad["runtime_doc_type"] = "historical_data"
    bad["output_relpath"] = "policy_doc/bad_doc.md"
    bad["cleaned_content_sha256"] = _write_doc(tmp_path, "policy_doc/bad_doc.md", "# Bad\n\nBody")
    manifest = _manifest(tmp_path, [good, bad])
    vector_root = tmp_path / "vector_store"

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_root=vector_root,
        write=True,
        strict=True,
        embedding_service=_FakeEmbedding(),
        vector_store=_FakeVectorStore(),
        chunk_store=ChunkTextStore(vector_root / "chunks.sqlite"),
    )

    assert result.mode == "blocked-rejected-records"
    assert result.written_chunk_count == 0
    assert result.plan.accepted_document_count == 1
    assert result.plan.rejected_reasons["invalid_runtime_doc_type"] == 1
    assert not (vector_root / "chunks.sqlite").exists()


def test_write_is_idempotent_for_same_manifest(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector = _FakeVectorStore()
    chunk_store = ChunkTextStore(tmp_path / "vector_store" / "chunks.sqlite")

    first = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_dir=tmp_path / "vector_store",
        write=True,
        embedding_service=_FakeEmbedding(),
        vector_store=vector,
        chunk_store=chunk_store,
    )
    second = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_dir=tmp_path / "vector_store",
        write=True,
        embedding_service=_FakeEmbedding(),
        vector_store=vector,
        chunk_store=chunk_store,
    )

    assert first.written_chunk_count == second.written_chunk_count == chunk_store.count()
    assert chunk_store.list_doc_ids() == ["fomc_statement_2026_06_17"]
    assert (tmp_path / "vector_store" / "ingest_audits" / "last_ingest_audit.json").exists()


def test_write_records_index_generation_metadata_without_raw_text(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_dir=vector_root,
        write=True,
        embedding_service=_FakeEmbedding(),
        vector_store=_FakeVectorStore(),
        chunk_store=ChunkTextStore(vector_root / "chunks.sqlite"),
    )

    payload = json.loads((vector_root / "index_generation.json").read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["schema_version"] == 1
    assert payload["generation_id"]
    assert payload["document_count"] == 1
    assert payload["chunk_count"] == result.chunk_count
    assert payload["written_chunk_count"] == result.written_chunk_count
    assert payload["embedding_model"] == "fake-bge"
    assert payload["embedding_dim"] == 2
    assert payload["chunking_version"] == "document_chunker_v1"
    assert "Federal funds target range" not in serialized


def test_vector_write_failure_does_not_overwrite_active_chunk_store(tmp_path):
    row = _base_row(tmp_path)
    row["cleaned_content_sha256"] = _write_doc(
        tmp_path,
        "policy_doc/fomc_statement_2026_06_17.md",
        "# FOMC Statement - 2026-06-17\n\nNew replacement text.",
    )
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    chunk_store = ChunkTextStore(vector_root / "chunks.sqlite")
    vector_store = _FailingVectorStore()
    chunk_store.upsert_chunk(
        StoredChunk(
            doc_id="fomc_statement_2026_06_17",
            chunk_index=0,
            text="old active chunk",
            title="Old active",
            doc_type="policy_doc",
            source_domain="www.federalreserve.gov",
            external_llm_context_allowed=True,
            evidence_tier="official_evidence",
            is_official_source=True,
        )
    )
    vector_store.upsert(
        "fomc_statement_2026_06_17",
        0,
        [1.0, 0.0],
        {
            "doc_id": "fomc_statement_2026_06_17",
            "chunk_index": 0,
            "doc_type": "policy_doc",
        },
    )
    _write_generation(vector_root)
    generation_before = (vector_root / "index_generation.json").read_text(encoding="utf-8")
    vector_store.fail_next_upsert = True

    try:
        ingest_curated_corpus(
            curated_root=tmp_path,
            manifest_path=manifest,
            vector_dir=vector_root,
            write=True,
            embedding_service=_FakeEmbedding(),
            vector_store=vector_store,
            chunk_store=chunk_store,
        )
    except RuntimeError as exc:
        assert str(exc) == "vector write failed"
    else:
        raise AssertionError("expected vector write failure")

    active = chunk_store.get_chunk("fomc_statement_2026_06_17", 0)
    assert active is not None
    assert active.text == "old active chunk"
    restored_vector = vector_store.items[("fomc_statement_2026_06_17", 0)]
    assert restored_vector[0] == [1.0, 0.0]
    assert restored_vector[1]["doc_type"] == "policy_doc"
    assert (vector_root / "index_generation.json").read_text(encoding="utf-8") == generation_before
    assert not (vector_root / "ingest_audits").exists()


def test_write_replace_existing_prunes_unknown_existing_docs(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector = _FakeVectorStore()
    chunk_store = ChunkTextStore(tmp_path / "vector_store" / "chunks.sqlite")
    chunk_store.upsert_chunk(
        StoredChunk(
            doc_id="old_hash_suffix_doc",
            chunk_index=0,
            text="old text",
            title="Old",
            doc_type="research_report",
            source_domain="local",
        )
    )
    _write_generation(tmp_path / "vector_store")

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_dir=tmp_path / "vector_store",
        write=True,
        replace_existing=True,
        embedding_service=_FakeEmbedding(),
        vector_store=vector,
        chunk_store=chunk_store,
    )

    assert result.mode == "write"
    assert result.pruned_document_count == 1
    assert chunk_store.list_doc_ids() == ["fomc_statement_2026_06_17"]
    assert "old_hash_suffix_doc" in vector.deleted


@pytest.mark.parametrize(
    ("generation", "expected_reason"),
    [
        ({"embedding_model": "other-model"}, "embedding_model_mismatch"),
        ({"embedding_dim": 3}, "embedding_dim_mismatch"),
        ({"chunking_version": "old_chunker"}, "chunking_version_mismatch"),
    ],
)
def test_write_preflight_rejects_existing_incompatible_index_before_any_write(
    tmp_path,
    generation,
    expected_reason,
):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    vector_store = _FakeVectorStore()
    chunk_store = _seed_existing_index(vector_root, vector_store, generation=generation)

    with pytest.raises(
        RuntimeError,
        match=f"index_compatibility_error:{expected_reason}",
    ):
        ingest_curated_corpus(
            curated_root=tmp_path,
            manifest_path=manifest,
            vector_dir=vector_root,
            write=True,
            embedding_service=_FakeEmbedding(),
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

    _assert_existing_index_unchanged(chunk_store, vector_store)


def test_write_preflight_rejects_existing_index_with_missing_generation_before_any_write(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    vector_store = _FakeVectorStore()
    chunk_store = _seed_existing_index(vector_root, vector_store)

    with pytest.raises(
        RuntimeError,
        match="index_compatibility_error:index_generation_missing_or_invalid",
    ):
        ingest_curated_corpus(
            curated_root=tmp_path,
            manifest_path=manifest,
            vector_dir=vector_root,
            write=True,
            embedding_service=_FakeEmbedding(),
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

    _assert_existing_index_unchanged(chunk_store, vector_store)


def test_write_preflight_rejects_existing_index_with_corrupt_generation_before_any_write(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    vector_store = _FakeVectorStore()
    chunk_store = _seed_existing_index(vector_root, vector_store)
    (vector_root / "index_generation.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="index_compatibility_error:index_generation_missing_or_invalid",
    ):
        ingest_curated_corpus(
            curated_root=tmp_path,
            manifest_path=manifest,
            vector_dir=vector_root,
            write=True,
            embedding_service=_FakeEmbedding(),
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

    _assert_existing_index_unchanged(chunk_store, vector_store)


def test_write_preflight_replace_existing_does_not_bypass_incompatibility(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    vector_store = _FakeVectorStore()
    chunk_store = _seed_existing_index(
        vector_root,
        vector_store,
        generation={"embedding_model": "other-model"},
    )

    with pytest.raises(
        RuntimeError,
        match="index_compatibility_error:embedding_model_mismatch",
    ):
        ingest_curated_corpus(
            curated_root=tmp_path,
            manifest_path=manifest,
            vector_dir=vector_root,
            write=True,
            replace_existing=True,
            embedding_service=_FakeEmbedding(),
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

    _assert_existing_index_unchanged(chunk_store, vector_store)


def test_write_preflight_allows_first_ingest_into_empty_root(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    vector_store = _FakeVectorStore()
    chunk_store = ChunkTextStore(vector_root / "chunks.sqlite")

    result = ingest_curated_corpus(
        curated_root=tmp_path,
        manifest_path=manifest,
        vector_dir=vector_root,
        write=True,
        embedding_service=_FakeEmbedding(),
        vector_store=vector_store,
        chunk_store=chunk_store,
    )

    assert result.mode == "write"
    assert result.written_chunk_count == chunk_store.count()
    assert vector_store.count() == result.written_chunk_count


def test_write_preflight_rejects_vector_enabled_index_when_embedding_runtime_unavailable(
    tmp_path,
    monkeypatch,
):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])
    vector_root = tmp_path / "vector_store"
    vector_store = _FakeVectorStore()
    chunk_store = _seed_existing_index(
        vector_root,
        vector_store,
        generation={"embedding_model": "fake-bge"},
    )
    monkeypatch.setitem(sys.modules, "llm.embedding_service", None)

    with pytest.raises(
        RuntimeError,
        match="index_compatibility_error:embedding_runtime_unavailable",
    ):
        ingest_curated_corpus(
            curated_root=tmp_path,
            manifest_path=manifest,
            vector_dir=vector_root,
            write=True,
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

    _assert_existing_index_unchanged(chunk_store, vector_store)
