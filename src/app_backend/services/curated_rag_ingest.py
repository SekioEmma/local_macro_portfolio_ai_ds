from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from llm.chunk_text_store import ChunkTextStore, StoredChunk
from llm.document_chunker import Chunk, chunk_text


ALLOWED_RUNTIME_DOC_TYPES = frozenset({"policy_doc", "research_report"})
ALLOWED_CONTENT_COHORTS = frozenset({"policy_doc", "research_report"})
READABLE_COHORTS = frozenset({"policy_doc", "research_report", "pending_governance", "review_required"})
DEFAULT_VECTOR_ROOT = Path(__file__).resolve().parents[3] / "data" / "vector_store"
DEFAULT_VECTOR_DIR = DEFAULT_VECTOR_ROOT


class CuratedRAGIngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class CuratedDocument:
    document_id: str
    path: Path
    title: str
    doc_type: str
    source_domain: str
    external_llm_context_allowed: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CuratedIngestPlan:
    curated_root: Path
    manifest_path: Path
    accepted: list[CuratedDocument]
    skipped_reasons: Counter[str]
    rejected_reasons: Counter[str]
    doc_type_counts: Counter[str]
    fomc_material_type_counts: Counter[str]

    @property
    def accepted_document_count(self) -> int:
        return len(self.accepted)


@dataclass(frozen=True)
class CuratedIngestResult:
    plan: CuratedIngestPlan
    chunk_count: int
    written_chunk_count: int
    mode: str


def build_ingest_plan(curated_root: Path, manifest_path: Path) -> CuratedIngestPlan:
    curated_root = curated_root.resolve()
    manifest_path = manifest_path.resolve()
    _validate_manifest_location(curated_root, manifest_path)
    rows = _read_manifest_rows(manifest_path)
    duplicate_ids = _duplicate_document_ids(rows)

    accepted: list[CuratedDocument] = []
    skipped: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    doc_types: Counter[str] = Counter()
    fomc_types: Counter[str] = Counter()

    for row in rows:
        decision, reason = _classify_row(row, duplicate_ids)
        if decision == "skipped":
            skipped[reason] += 1
            continue
        if decision == "rejected":
            rejected[reason] += 1
            continue
        try:
            document = _document_from_row(curated_root, row)
        except CuratedRAGIngestError as exc:
            rejected[str(exc)] += 1
            continue
        accepted.append(document)
        doc_types[document.doc_type] += 1
        material_type = document.metadata.get("fomc_material_type")
        if isinstance(material_type, str) and material_type:
            fomc_types[material_type] += 1

    return CuratedIngestPlan(
        curated_root=curated_root,
        manifest_path=manifest_path,
        accepted=accepted,
        skipped_reasons=skipped,
        rejected_reasons=rejected,
        doc_type_counts=doc_types,
        fomc_material_type_counts=fomc_types,
    )


def ingest_curated_corpus(
    *,
    curated_root: Path,
    manifest_path: Path,
    write: bool,
    vector_root: Path = DEFAULT_VECTOR_ROOT,
    vector_dir: Path | None = None,
    offline_only: bool = True,
    strict: bool = False,
    embedding_service: Any | None = None,
    vector_store: Any | None = None,
    chunk_store: ChunkTextStore | None = None,
) -> CuratedIngestResult:
    if vector_dir is not None:
        vector_root = vector_dir
    plan = build_ingest_plan(curated_root, manifest_path)
    chunk_count = sum(len(chunk_text(doc.path.read_text(encoding="utf-8"), doc_id=doc.document_id)) for doc in plan.accepted)

    if not write:
        return CuratedIngestResult(plan=plan, chunk_count=chunk_count, written_chunk_count=0, mode="dry-run")
    if not plan.accepted:
        return CuratedIngestResult(plan=plan, chunk_count=0, written_chunk_count=0, mode="blocked-no-eligible")
    if strict and plan.rejected_reasons:
        return CuratedIngestResult(plan=plan, chunk_count=chunk_count, written_chunk_count=0, mode="blocked-rejected-records")

    vector_root = vector_root.resolve()

    if embedding_service is None:
        from llm.embedding_service import EmbeddingService

        embedding_service = EmbeddingService(offline_only=offline_only)
        embedding_service.load()

    chunk_store = chunk_store or ChunkTextStore(vector_root / "chunks.sqlite")
    _guard_existing_docs(chunk_store, {doc.document_id for doc in plan.accepted})

    if vector_store is None:
        from llm.vector_store import VectorStore

        vector_store = VectorStore(vector_root / "chroma")

    written = 0
    for doc in plan.accepted:
        text = doc.path.read_text(encoding="utf-8")
        chunks = chunk_text(text, doc_id=doc.document_id)
        chunk_store.delete_doc(doc.document_id)
        vector_store.delete(doc.document_id)
        if not chunks:
            continue
        embeddings = embedding_service.encode([chunk.text for chunk in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            chunk_store.upsert_chunk(_stored_chunk(doc, chunk))
            vector_store.upsert(
                doc_id=chunk.doc_id,
                chunk_index=chunk.chunk_index,
                embedding=embedding,
                metadata=_vector_metadata(doc),
            )
            written += 1
    result = CuratedIngestResult(plan=plan, chunk_count=chunk_count, written_chunk_count=written, mode="write")
    _write_ingest_audit(vector_root, result)
    return result


def summarize_plan(plan: CuratedIngestPlan) -> dict[str, Any]:
    return {
        "curated_root": str(plan.curated_root),
        "manifest": str(plan.manifest_path),
        "accepted_documents": plan.accepted_document_count,
        "skipped_reasons": dict(sorted(plan.skipped_reasons.items())),
        "rejected_reasons": dict(sorted(plan.rejected_reasons.items())),
        "doc_type_counts": dict(sorted(plan.doc_type_counts.items())),
        "fomc_material_type_counts": dict(sorted(plan.fomc_material_type_counts.items())),
    }


def summarize_result(result: CuratedIngestResult) -> dict[str, Any]:
    payload = summarize_plan(result.plan)
    payload.update({
        "mode": result.mode,
        "candidate_chunks": result.chunk_count,
        "written_chunks": result.written_chunk_count,
    })
    return payload


def _write_ingest_audit(vector_root: Path, result: CuratedIngestResult) -> None:
    audit_dir = vector_root / "ingest_audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    payload = summarize_result(result)
    payload["created_at_utc"] = datetime.now(UTC).isoformat()
    (audit_dir / "last_ingest_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_manifest_location(curated_root: Path, manifest_path: Path) -> None:
    expected_parent = curated_root / "metadata"
    if manifest_path.parent != expected_parent:
        raise CuratedRAGIngestError("manifest_outside_curated_metadata")
    if manifest_path.suffix != ".jsonl":
        raise CuratedRAGIngestError("unexpected_manifest_name")


def _read_manifest_rows(manifest_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _duplicate_document_ids(rows: list[dict[str, Any]]) -> set[str]:
    counts = Counter(row.get("document_id") for row in rows if isinstance(row.get("document_id"), str))
    return {doc_id for doc_id, count in counts.items() if count > 1}


def _classify_row(row: dict[str, Any], duplicate_ids: set[str]) -> tuple[str, str]:
    document_id = row.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        return "rejected", "missing_document_id"
    if document_id in duplicate_ids:
        return "rejected", "duplicate_document_id"

    cohort = row.get("cohort")
    if cohort not in READABLE_COHORTS and cohort not in {"local_only", "unsupported"}:
        return "rejected", "unknown_cohort"
    if cohort not in ALLOWED_CONTENT_COHORTS:
        return "skipped", f"cohort_{cohort}"

    if row.get("extraction_status") != "ready":
        return "skipped", f"extraction_{row.get('extraction_status')}"
    if row.get("provenance_status") != "verified":
        return "skipped", f"provenance_{row.get('provenance_status')}"
    if row.get("ingest_status") != "eligible":
        return "skipped", f"ingest_{row.get('ingest_status')}"
    if row.get("external_llm_context_allowed") is not True:
        return "rejected", "external_llm_context_not_allowed"
    if row.get("allowed_use") != "external_context_candidate":
        return "rejected", "allowed_use_not_external_context_candidate"
    if row.get("runtime_doc_type") not in ALLOWED_RUNTIME_DOC_TYPES:
        return "rejected", "invalid_runtime_doc_type"

    canonical_url = row.get("canonical_url")
    source_domain = row.get("source_domain")
    if not isinstance(canonical_url, str) or not canonical_url.strip():
        return "rejected", "missing_canonical_url"
    if not isinstance(source_domain, str) or not source_domain.strip():
        return "rejected", "missing_source_domain"
    if _url_host(canonical_url) != _normal_host(source_domain):
        return "rejected", "canonical_url_source_domain_mismatch"
    return "accepted", "accepted"


def _document_from_row(curated_root: Path, row: dict[str, Any]) -> CuratedDocument:
    output_relpath = row.get("output_relpath")
    if not isinstance(output_relpath, str) or not output_relpath.strip():
        raise CuratedRAGIngestError("missing_output_relpath")
    relpath = Path(output_relpath)
    if relpath.is_absolute() or ".." in relpath.parts:
        raise CuratedRAGIngestError("unsafe_output_relpath")
    if not relpath.parts or relpath.parts[0] not in ALLOWED_CONTENT_COHORTS:
        raise CuratedRAGIngestError("output_relpath_not_seedable_cohort")

    path = (curated_root / relpath).resolve()
    if not path.is_relative_to(curated_root):
        raise CuratedRAGIngestError("output_path_escapes_curated_root")
    if path.suffix.lower() not in {".md", ".txt"}:
        raise CuratedRAGIngestError("unsupported_output_extension")
    if not path.exists():
        raise CuratedRAGIngestError("output_file_missing")

    content = path.read_bytes()
    expected_hash = row.get("cleaned_content_sha256")
    if not isinstance(expected_hash, str) or hashlib.sha256(content).hexdigest() != expected_hash:
        raise CuratedRAGIngestError("cleaned_content_hash_mismatch")

    text = content.decode("utf-8", errors="replace")
    return CuratedDocument(
        document_id=row["document_id"],
        path=path,
        title=_title_from_markdown(text, row["document_id"]),
        doc_type=row["runtime_doc_type"],
        source_domain=_normal_host(row["source_domain"]),
        external_llm_context_allowed=True,
        metadata=_safe_metadata(row),
    )


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if title:
                return title
    return fallback


def _safe_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "title": _metadata_str(row.get("title")),
        "doc_type": row["runtime_doc_type"],
        "source_domain": _normal_host(row["source_domain"]),
        "external_llm_context_allowed": True,
        "source_kind": _metadata_str(row.get("source_kind")),
        "temporal_status": _metadata_str(row.get("temporal_status")),
        "release_date": _metadata_str(row.get("release_date")),
        "fomc_material_type": _metadata_str(row.get("fomc_material_type")),
    }
    return {key: value for key, value in metadata.items() if value not in (None, "")}


def _metadata_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _stored_chunk(doc: CuratedDocument, chunk: Chunk) -> StoredChunk:
    return StoredChunk(
        doc_id=doc.document_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        title=doc.title,
        doc_type=doc.doc_type,
        source_domain=doc.source_domain,
        external_llm_context_allowed=doc.external_llm_context_allowed,
    )


def _vector_metadata(doc: CuratedDocument) -> dict[str, Any]:
    metadata = dict(doc.metadata)
    metadata["title"] = doc.title
    metadata["doc_type"] = doc.doc_type
    metadata["source_domain"] = doc.source_domain
    metadata["external_llm_context_allowed"] = doc.external_llm_context_allowed
    return metadata


def _guard_existing_docs(chunk_store: ChunkTextStore, accepted_doc_ids: set[str]) -> None:
    existing = set(chunk_store.list_doc_ids())
    unknown = existing - accepted_doc_ids
    if unknown:
        raise CuratedRAGIngestError("existing_unknown_documents_block_write")


def _url_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    return parsed.hostname.lower().strip(".")


def _normal_host(host: str) -> str:
    parsed = urlparse(host if "://" in host else f"https://{host}")
    return (parsed.hostname or "").lower().strip(".")
