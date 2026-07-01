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

from app_backend.services.rag_index_generation import (
    build_index_generation_metadata,
    write_index_generation_metadata,
)


ALLOWED_RUNTIME_DOC_TYPES = frozenset({"policy_doc", "research_report", "official_release"})
ALLOWED_CONTENT_COHORTS = frozenset({"policy_doc", "research_report", "official_release"})
ALLOWED_EVIDENCE_TIERS = frozenset({"official_evidence", "institutional_view"})
OFFICIAL_SOURCE_KINDS = frozenset({"central_bank_policy", "official_release", "official_outlook"})
READABLE_COHORTS = frozenset({
    "policy_doc",
    "research_report",
    "official_release",
    "pending_governance",
    "review_required",
})
_COHORT_PRIORITY = {"policy_doc": 0, "official_release": 1, "research_report": 2, "review_required": 3}
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
    evidence_tier: str
    is_official_source: bool
    metadata: dict[str, Any]
    cleaned_content_sha256: str
    verified_text: str = ""


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
    pruned_document_count: int = 0


@dataclass(frozen=True)
class _PreparedDocument:
    document: CuratedDocument
    chunks: list[Chunk]
    stored_chunks: list[StoredChunk]
    embeddings: list[list[float]]


def build_ingest_plan(curated_root: Path, manifest_path: Path) -> CuratedIngestPlan:
    curated_root = curated_root.resolve()
    manifest_path = manifest_path.resolve()
    _validate_manifest_location(curated_root, manifest_path)
    rows = _read_manifest_rows(manifest_path)
    rows, dedup_skipped = _deduplicate_identical_documents(rows)
    duplicate_ids = _duplicate_document_ids(rows)

    accepted: list[CuratedDocument] = []
    skipped: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    doc_types: Counter[str] = Counter()
    fomc_types: Counter[str] = Counter()
    skipped.update(dedup_skipped)

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
    replace_existing: bool = False,
    embedding_service: Any | None = None,
    vector_store: Any | None = None,
    chunk_store: ChunkTextStore | None = None,
) -> CuratedIngestResult:
    if vector_dir is not None:
        vector_root = vector_dir
    plan = build_ingest_plan(curated_root, manifest_path)
    chunk_count = sum(len(chunk_text(doc.verified_text, doc_id=doc.document_id)) for doc in plan.accepted)

    if not write:
        return CuratedIngestResult(plan=plan, chunk_count=chunk_count, written_chunk_count=0, mode="dry-run")
    if not plan.accepted:
        return CuratedIngestResult(plan=plan, chunk_count=0, written_chunk_count=0, mode="blocked-no-eligible")
    if strict and plan.rejected_reasons:
        return CuratedIngestResult(plan=plan, chunk_count=chunk_count, written_chunk_count=0, mode="blocked-rejected-records")

    vector_root = vector_root.resolve()

    chunk_store = chunk_store or ChunkTextStore(vector_root / "chunks.sqlite")
    unknown_existing = _unknown_existing_docs(chunk_store, {doc.document_id for doc in plan.accepted})
    if unknown_existing and not replace_existing:
        raise CuratedRAGIngestError("existing_unknown_documents_block_write")

    vector_enabled = True
    if embedding_service is None:
        try:
            from llm.embedding_service import EmbeddingService

            embedding_service = EmbeddingService(offline_only=offline_only)
            embedding_service.load()
        except ImportError:
            embedding_service = None
            vector_enabled = False

    if vector_enabled and vector_store is None:
        from llm.vector_store import VectorStore

        vector_store = VectorStore(vector_root / "chroma")

    prepared_docs = _prepare_documents(plan.accepted, embedding_service)
    affected_doc_ids = unknown_existing | {doc.document_id for doc in plan.accepted}
    chunk_snapshot = _snapshot_chunks(chunk_store, affected_doc_ids)

    try:
        if vector_enabled and vector_store is not None:
            for doc_id in sorted(unknown_existing):
                vector_store.delete(doc_id)
            for prepared in prepared_docs:
                vector_store.delete(prepared.document.document_id)
                if prepared.chunks:
                    _upsert_vector_chunks(
                        vector_store,
                        prepared.document,
                        prepared.chunks,
                        prepared.embeddings,
                    )

        for doc_id in sorted(unknown_existing):
            chunk_store.delete_doc(doc_id)
        for prepared in prepared_docs:
            chunk_store.delete_doc(prepared.document.document_id)
            if prepared.stored_chunks:
                chunk_store.upsert_chunks(prepared.stored_chunks)
    except Exception:
        _restore_chunks(chunk_store, affected_doc_ids, chunk_snapshot)
        raise

    written = sum(len(prepared.stored_chunks) for prepared in prepared_docs)
    mode = "write" if vector_enabled else "write-bm25-only"
    result = CuratedIngestResult(
        plan=plan,
        chunk_count=chunk_count,
        written_chunk_count=written,
        mode=mode,
        pruned_document_count=len(unknown_existing),
    )
    _write_ingest_audit(vector_root, result)
    _write_index_generation(vector_root, result, vector_enabled, embedding_service)
    _invalidate_runtime_cache(vector_root)
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
        "pruned_documents": result.pruned_document_count,
    })
    return payload


def _prepare_documents(
    documents: list[CuratedDocument],
    embedding_service: Any | None,
) -> list[_PreparedDocument]:
    prepared: list[_PreparedDocument] = []
    for doc in documents:
        chunks = chunk_text(doc.verified_text, doc_id=doc.document_id)
        embeddings = (
            embedding_service.encode([chunk.text for chunk in chunks])
            if embedding_service is not None and chunks
            else []
        )
        prepared.append(
            _PreparedDocument(
                document=doc,
                chunks=chunks,
                stored_chunks=[_stored_chunk(doc, chunk) for chunk in chunks],
                embeddings=embeddings,
            )
        )
    return prepared


def _snapshot_chunks(
    chunk_store: ChunkTextStore,
    doc_ids: set[str],
) -> dict[str, list[StoredChunk]]:
    if not doc_ids:
        return {}
    snapshot: dict[str, list[StoredChunk]] = {doc_id: [] for doc_id in doc_ids}
    for chunk in chunk_store.list_chunks():
        if chunk.doc_id in snapshot:
            snapshot[chunk.doc_id].append(chunk)
    return snapshot


def _restore_chunks(
    chunk_store: ChunkTextStore,
    doc_ids: set[str],
    snapshot: dict[str, list[StoredChunk]],
) -> None:
    for doc_id in sorted(doc_ids):
        chunk_store.delete_doc(doc_id)
        chunks = snapshot.get(doc_id, [])
        if chunks:
            chunk_store.upsert_chunks(chunks)


def _write_ingest_audit(vector_root: Path, result: CuratedIngestResult) -> None:
    audit_dir = vector_root / "ingest_audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    payload = summarize_result(result)
    payload["created_at_utc"] = datetime.now(UTC).isoformat()
    (audit_dir / "last_ingest_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_index_generation(
    vector_root: Path,
    result: CuratedIngestResult,
    vector_enabled: bool,
    embedding_service: Any | None,
) -> None:
    payload = build_index_generation_metadata(
        documents=result.plan.accepted,
        mode=result.mode,
        chunk_count=result.chunk_count,
        written_chunk_count=result.written_chunk_count,
        pruned_document_count=result.pruned_document_count,
        vector_enabled=vector_enabled,
        embedding_service=embedding_service,
    )
    write_index_generation_metadata(vector_root, payload)


def _invalidate_runtime_cache(vector_root: Path) -> None:
    from app_backend.services.local_rag_runtime_factory import (
        invalidate_local_rag_runtime_cache,
    )

    invalidate_local_rag_runtime_cache(vector_root)


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


def _deduplicate_identical_documents(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Collapse rows sharing both document_id and cleaned_content_sha256.

    Same id + same content across cohorts is a legitimate cross-cohort copy
    (a user-curated original was placed in two cohort folders). Keep the
    highest-priority cohort and skip the rest with reason 'duplicate_cohort_copy'.
    Rows with same id but DIFFERENT sha256 are left untouched so the existing
    duplicate_document_id rejection still fires.
    """
    by_id: dict[str, list[dict[str, Any]]] = {}
    order: list[str | None] = []
    seen_keys: set[str] = set()
    for row in rows:
        doc_id = row.get("document_id")
        if isinstance(doc_id, str):
            by_id.setdefault(doc_id, []).append(row)
            if doc_id not in seen_keys:
                seen_keys.add(doc_id)
                order.append(doc_id)
        else:
            order.append(None)

    skipped: Counter[str] = Counter()
    surviving: dict[str, dict[str, Any]] = {}
    for doc_id, group in by_id.items():
        if len(group) == 1:
            surviving[doc_id] = group[0]
            continue
        hashes = {row.get("cleaned_content_sha256") for row in group}
        if len(hashes) > 1 or None in hashes:
            for row in group:
                surviving.setdefault(f"__keep_dup__{id(row)}", row)
            continue
        winner = min(group, key=lambda r: (_COHORT_PRIORITY.get(r.get("cohort", ""), 99), group.index(r)))
        skipped["duplicate_cohort_copy"] += len(group) - 1
        surviving[doc_id] = winner

    result: list[dict[str, Any]] = []
    placed: set[str] = set()
    for key in order:
        if key is None or key not in by_id:
            continue
        if key in placed:
            continue
        placed.add(key)
        group = by_id[key]
        if key in surviving:
            result.append(surviving[key])
        else:
            for row in group:
                marker = f"__keep_dup__{id(row)}"
                if marker in surviving:
                    result.append(row)
    return result, skipped


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
    evidence_decision = _validate_evidence_tier(row)
    if evidence_decision is not None:
        return "rejected", evidence_decision

    canonical_url = row.get("canonical_url")
    source_domain = row.get("source_domain")
    if isinstance(canonical_url, str) and canonical_url.strip():
        if not isinstance(source_domain, str) or not source_domain.strip():
            return "rejected", "missing_source_domain"
        if _url_host(canonical_url) != _normal_host(source_domain):
            return "rejected", "canonical_url_source_domain_mismatch"
    elif not _has_verified_local_provenance(row):
        return "rejected", "missing_canonical_url"
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
    if not isinstance(expected_hash, str) or _cleaned_content_sha256(content) != expected_hash:
        raise CuratedRAGIngestError("cleaned_content_hash_mismatch")

    text = content.decode("utf-8", errors="replace")
    return CuratedDocument(
        document_id=row["document_id"],
        path=path,
        title=_title_from_markdown(text, row["document_id"]),
        doc_type=row["runtime_doc_type"],
        source_domain=_source_label(row),
        external_llm_context_allowed=bool(row["external_llm_context_allowed"]),
        evidence_tier=_evidence_tier(row),
        is_official_source=_is_official_source(row),
        metadata=_safe_metadata(row),
        cleaned_content_sha256=expected_hash,
        verified_text=text,
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
        "source_domain": _source_label(row),
        "external_llm_context_allowed": bool(row.get("external_llm_context_allowed")),
        "evidence_tier": _evidence_tier(row),
        "is_official_source": _is_official_source(row),
        "source_kind": _metadata_str(row.get("source_kind")),
        "temporal_status": _metadata_str(row.get("temporal_status")),
        "release_date": _metadata_str(row.get("release_date")),
        "observation_period": _metadata_str(row.get("observation_period")),
        "material_type": _metadata_str(row.get("material_type")),
        "factual_status": _metadata_str(row.get("factual_status")),
        "vintage": _metadata_str(row.get("vintage")),
        "table_quality": _metadata_str(row.get("table_quality")),
        "content_layers": _metadata_list(row.get("content_layers")),
        "fomc_material_type": _metadata_str(row.get("fomc_material_type")),
    }
    return {key: value for key, value in metadata.items() if value not in (None, "")}


def _metadata_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _metadata_list(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    items = [item for item in value if isinstance(item, str) and item]
    return ",".join(items) if items else None


def _stored_chunk(doc: CuratedDocument, chunk: Chunk) -> StoredChunk:
    return StoredChunk(
        doc_id=doc.document_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        title=doc.title,
        doc_type=doc.doc_type,
        source_domain=doc.source_domain,
        external_llm_context_allowed=doc.external_llm_context_allowed,
        evidence_tier=doc.evidence_tier,
        is_official_source=doc.is_official_source,
    )


def _vector_metadata(doc: CuratedDocument) -> dict[str, Any]:
    metadata = dict(doc.metadata)
    metadata["title"] = doc.title
    metadata["doc_type"] = doc.doc_type
    metadata["source_domain"] = doc.source_domain
    metadata["external_llm_context_allowed"] = doc.external_llm_context_allowed
    metadata["evidence_tier"] = doc.evidence_tier
    metadata["is_official_source"] = doc.is_official_source
    return metadata


def _upsert_vector_chunks(
    vector_store: Any,
    doc: CuratedDocument,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    metadata = _vector_metadata(doc)
    if hasattr(vector_store, "upsert_many"):
        vector_store.upsert_many([
            (chunk.doc_id, chunk.chunk_index, embeddings[index], metadata)
            for index, chunk in enumerate(chunks)
        ])
        return
    for index, chunk in enumerate(chunks):
        vector_store.upsert(
            doc_id=chunk.doc_id,
            chunk_index=chunk.chunk_index,
            embedding=embeddings[index],
            metadata=metadata,
        )


def _unknown_existing_docs(chunk_store: ChunkTextStore, accepted_doc_ids: set[str]) -> set[str]:
    existing = set(chunk_store.list_doc_ids())
    return existing - accepted_doc_ids


def _url_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    return parsed.hostname.lower().strip(".")


def _normal_host(host: str) -> str:
    parsed = urlparse(host if "://" in host else f"https://{host}")
    return (parsed.hostname or "").lower().strip(".")


def _validate_evidence_tier(row: dict[str, Any]) -> str | None:
    tier = _evidence_tier(row)
    if tier not in ALLOWED_EVIDENCE_TIERS:
        return "invalid_evidence_tier"
    source_kind = row.get("source_kind")
    runtime_doc_type = row.get("runtime_doc_type")
    is_official = _is_official_source(row)

    if source_kind == "institutional_research":
        if tier != "institutional_view":
            return "institutional_research_not_view_tier"
        if is_official:
            return "institutional_research_marked_official"
        if runtime_doc_type != "research_report":
            return "institutional_research_invalid_runtime_doc_type"
        return None

    if tier == "institutional_view":
        return "institutional_view_requires_institutional_research"
    if tier == "official_evidence" and source_kind not in OFFICIAL_SOURCE_KINDS:
        return "official_evidence_requires_official_source_kind"
    if tier == "official_evidence" and not is_official:
        return "official_evidence_requires_official_source_flag"
    return None


def _evidence_tier(row: dict[str, Any]) -> str:
    value = row.get("evidence_tier")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if row.get("source_kind") == "institutional_research":
        return "institutional_view"
    if row.get("source_kind") in OFFICIAL_SOURCE_KINDS:
        return "official_evidence"
    return "unknown"


def _is_official_source(row: dict[str, Any]) -> bool:
    value = row.get("is_official_source")
    if isinstance(value, bool):
        return value
    if row.get("source_kind") in OFFICIAL_SOURCE_KINDS:
        return True
    return False


def _cleaned_content_sha256(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _has_verified_local_provenance(row: dict[str, Any]) -> bool:
    if not _has_local_source_file_markers(row):
        return False
    if (
        row.get("admission_source") == "source_ledger"
        and row.get("admission_status") == "verified"
        and row.get("verified_by") == "user"
        and row.get("verification_basis") == "user_curated_local_file"
    ):
        return True
    return row.get("provenance_status") == "verified"


def _has_local_source_file_markers(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get("source_relpath"), str)
        and bool(row["source_relpath"].strip())
        and isinstance(row.get("source_file_sha256"), str)
        and bool(row["source_file_sha256"].strip())
    )


def _source_label(row: dict[str, Any]) -> str:
    source_domain = row.get("source_domain")
    if isinstance(source_domain, str) and source_domain.strip():
        return _normal_host(source_domain)
    if _has_verified_local_provenance(row):
        return "local_user_verified"
    return "unknown"
