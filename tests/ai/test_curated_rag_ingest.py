from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app_backend.services.curated_rag_ingest import build_ingest_plan, ingest_curated_corpus
from llm.chunk_text_store import ChunkTextStore


class _FakeEmbedding:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


class _FakeVectorStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, int, dict[str, object]]] = []
        self.deleted: list[str] = []

    def delete(self, doc_id: str) -> int:
        self.deleted.append(doc_id)
        self.upserts = [item for item in self.upserts if item[0] != doc_id]
        return 0

    def upsert(self, doc_id: str, chunk_index: int, embedding: list[float], metadata: dict[str, object]) -> None:
        self.upserts.append((doc_id, chunk_index, metadata))


def _write_doc(root: Path, relpath: str, text: str) -> str:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "canonical_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
        "source_domain": "www.federalreserve.gov",
        "cleaned_content_sha256": digest,
        "source_kind": "central_bank_policy",
        "temporal_status": "as_released",
        "release_date": "2026-06-17",
        "fomc_material_type": "statement",
    }


def _manifest(root: Path, rows: list[dict[str, object]]) -> Path:
    metadata = root / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    path = metadata / "rag_manifest.jsonl"
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows), encoding="utf-8")
    return path


def test_eligible_manifest_document_can_be_planned(tmp_path):
    row = _base_row(tmp_path)
    manifest = _manifest(tmp_path, [row])

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
