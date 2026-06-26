#!/usr/bin/env python3
"""Seed the RAG knowledge base from staged local text files.

Usage:
    python scripts/seed_knowledge_base.py                  # dry-run: shows what would be indexed
    python scripts/seed_knowledge_base.py --write          # write chunk text store + vector store
    python scripts/seed_knowledge_base.py --doc-type research_report  # override doc_type
    python scripts/seed_knowledge_base.py --scan-dir /path/to/files   # custom input dir
    python scripts/seed_knowledge_base.py --manifest /path/to/rag_manifest.jsonl

Supported file extensions: .txt, .md
Each file is split into overlapping chunks, embedded, and stored in:
    data/vector_store/          (Chroma + chunk_text store)

Default input directory: data/knowledge_base/input/
Each .txt or .md file is treated as one document.
Filename (without extension) is used as the title unless a first-line H1 is found.
doc_type defaults to "research_report"; override with --doc-type.

This script never calls Tavily, never reads .env, never touches existing
knowledge_base.sqlite or economic_calendar.sqlite.  Network access: none.
Real embedding requires sentence-transformers (pip install sentence-transformers).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llm.document_chunker import chunk_text  # noqa: E402
from llm.chunk_text_store import ChunkTextStore, StoredChunk  # noqa: E402

_DEFAULT_INPUT_DIR = ROOT / "data" / "knowledge_base" / "input"
_DEFAULT_VECTOR_DIR = ROOT / "data" / "vector_store"
_CHUNK_TEXT_DB = _DEFAULT_VECTOR_DIR / "chunks.sqlite"
_VALID_DOC_TYPES = {"policy_doc", "research_report", "historical_data", "one_shot_news"}
_EXTENSIONS = {".txt", ".md"}
_MANIFEST_DEFAULT_COHORTS = {"policy_doc", "research_report"}


@dataclass(frozen=True)
class SeedDocument:
    path: Path
    doc_id: str
    doc_type: str
    external_llm_context_allowed: bool


def _doc_id_for_file(path: Path) -> str:
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return f"{path.stem[:40]}_{content_hash}"


def _title_from_file(path: Path, text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    if first.startswith("# "):
        return first[2:].strip()
    return path.stem.replace("_", " ").replace("-", " ").title()


def _source_domain_for(path: Path) -> str:
    return "local"


def _scan_dir_documents(
    scan_dir: Path,
    *,
    doc_type: str,
    external_llm_context_allowed: bool,
) -> list[SeedDocument]:
    files = sorted(p for p in scan_dir.iterdir() if p.suffix in _EXTENSIONS) if scan_dir.exists() else []
    return [
        SeedDocument(
            path=fpath,
            doc_id=_doc_id_for_file(fpath),
            doc_type=doc_type,
            external_llm_context_allowed=external_llm_context_allowed,
        )
        for fpath in files
    ]


def _manifest_documents(
    manifest_path: Path,
    *,
    include_review_required: bool = False,
) -> list[SeedDocument]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    staging_root = manifest_path.parent.parent
    allowed_cohorts = set(_MANIFEST_DEFAULT_COHORTS)
    if include_review_required:
        allowed_cohorts.add("review_required")

    documents: list[SeedDocument] = []
    for line_no, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not _manifest_row_is_external_seed_candidate(row, allowed_cohorts):
            continue

        output_relpath = row.get("output_relpath")
        relpath = Path(output_relpath)
        if relpath.is_absolute() or ".." in relpath.parts:
            raise ValueError(f"manifest line {line_no}: unsafe output_relpath: {output_relpath!r}")
        doc_path = (staging_root / relpath).resolve()
        if not doc_path.is_relative_to(staging_root.resolve()):
            raise ValueError(f"manifest line {line_no}: output path escapes staging root")
        if doc_path.suffix not in _EXTENSIONS:
            raise ValueError(f"manifest line {line_no}: unsupported output extension: {output_relpath!r}")
        if not doc_path.exists():
            raise FileNotFoundError(f"manifest line {line_no}: staged file not found: {doc_path}")

        expected_hash = row.get("cleaned_content_sha256")
        if isinstance(expected_hash, str) and expected_hash:
            content = doc_path.read_bytes()
            text_normalized = content.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            actual_hash = hashlib.sha256(text_normalized.encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(f"manifest line {line_no}: content hash mismatch for {output_relpath!r}")

        documents.append(
            SeedDocument(
                path=doc_path,
                doc_id=row["document_id"],
                doc_type=row["runtime_doc_type"],
                external_llm_context_allowed=True,
            )
        )
    return documents


def _manifest_row_is_external_seed_candidate(row: dict[str, object], allowed_cohorts: set[str]) -> bool:
    return (
        row.get("cohort") in allowed_cohorts
        and row.get("ingest_status") == "eligible"
        and row.get("extraction_status") == "ready"
        and row.get("provenance_status") == "verified"
        and row.get("external_llm_context_allowed") is True
        and row.get("allowed_use") == "external_context_candidate"
        and row.get("runtime_doc_type") in _VALID_DOC_TYPES
        and isinstance(row.get("document_id"), str)
        and isinstance(row.get("output_relpath"), str)
    )


def seed(
    *,
    scan_dir: Path,
    vector_dir: Path,
    doc_type: str,
    write: bool,
    external_llm_context_allowed: bool = True,
    manifest_path: Path | None = None,
    include_review_required: bool = False,
    verbose: bool = True,
) -> dict[str, int]:
    if doc_type not in _VALID_DOC_TYPES:
        raise ValueError(f"doc_type must be one of {sorted(_VALID_DOC_TYPES)}, got {doc_type!r}")

    if manifest_path is not None:
        documents = _manifest_documents(
            manifest_path,
            include_review_required=include_review_required,
        )
    else:
        documents = _scan_dir_documents(
            scan_dir,
            doc_type=doc_type,
            external_llm_context_allowed=external_llm_context_allowed,
        )

    if not documents:
        if verbose:
            source = f"manifest candidates in {manifest_path}" if manifest_path else f".txt/.md files in {scan_dir}"
            print(f"No seedable {source}")
        return {"files": 0, "chunks": 0, "written": 0}

    chunk_store = ChunkTextStore(_CHUNK_TEXT_DB) if write else None

    vs = None
    emb_svc = None
    vector_enabled = False
    if write:
        try:
            from llm.vector_store import VectorStore
            from llm.embedding_service import EmbeddingService
            emb_svc_candidate = EmbeddingService()
            emb_svc_candidate.load()
            vs = VectorStore(vector_dir / "chroma")
            emb_svc = emb_svc_candidate
            vector_enabled = True
        except ImportError as exc:
            if verbose:
                print(f"[warn] vector store unavailable ({exc}); writing BM25-only chunks")

    total_chunks = 0
    total_written = 0

    for document in documents:
        fpath = document.path
        text = fpath.read_text(encoding="utf-8", errors="replace")
        title = _title_from_file(fpath, text)
        source_domain = _source_domain_for(fpath)
        chunks = chunk_text(text, doc_id=document.doc_id)
        total_chunks += len(chunks)

        if verbose:
            llm_flag = "llm=yes" if document.external_llm_context_allowed else "llm=no(local-only)"
            mode_label = "[dry-run]" if not write else ("[write]" if vector_enabled else "[write-bm25-only]")
            print(
                f"  {mode_label} {fpath.name} -> {len(chunks)} chunks  "
                f"doc_id={document.doc_id}  doc_type={document.doc_type}  {llm_flag}"
            )

        if not write or chunk_store is None or not chunks:
            continue

        embeddings = emb_svc.encode([c.text for c in chunks]) if vector_enabled else []
        for index, chunk in enumerate(chunks):
            stored = StoredChunk(
                doc_id=chunk.doc_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                title=title,
                doc_type=document.doc_type,
                source_domain=source_domain,
                external_llm_context_allowed=document.external_llm_context_allowed,
            )
            chunk_store.upsert_chunk(stored)
            if vector_enabled and vs is not None:
                vs.upsert(
                    doc_id=chunk.doc_id,
                    chunk_index=chunk.chunk_index,
                    embedding=embeddings[index],
                    metadata={
                        "title": title,
                        "doc_type": document.doc_type,
                        "source_domain": source_domain,
                        "external_llm_context_allowed": document.external_llm_context_allowed,
                    },
                )
            total_written += 1

    if verbose:
        print(f"\nSummary: {len(documents)} file(s), {total_chunks} chunk(s), {total_written} written.")
        if not write:
            print("Run with --write to actually index.")

    return {"files": len(documents), "chunks": total_chunks, "written": total_written}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="Write chunks to vector store (default: dry-run)")
    parser.add_argument("--doc-type", default="research_report", help="Document type for all files in this run")
    parser.add_argument("--scan-dir", type=Path, default=_DEFAULT_INPUT_DIR, help="Directory to scan for .txt/.md files")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Read a macro-rag-corpus-curator rag_manifest.jsonl and seed only eligible external candidates",
    )
    parser.add_argument(
        "--include-review-required",
        action="store_true",
        help="Also seed review_required manifest rows when they otherwise pass external-context gates",
    )
    parser.add_argument(
        "--no-external-llm-context",
        action="store_true",
        help="Mark all chunks as local-only (external_llm_context_allowed=False). "
             "Use for private/copyrighted documents that must not reach any LLM.",
    )
    args = parser.parse_args()

    external_llm_context_allowed = not args.no_external_llm_context

    print(f"Mode: {'WRITE' if args.write else 'DRY-RUN'}")
    if args.manifest:
        print(f"Manifest: {args.manifest}")
        print("Manifest gates: eligible + ready + verified + external_context_candidate")
        print(f"review_required: {'included' if args.include_review_required else 'excluded'}\n")
    else:
        print(f"Scanning: {args.scan_dir}")
        print(f"doc_type: {args.doc_type}")
        print(f"external_llm_context: {'yes' if external_llm_context_allowed else 'NO - local-only'}\n")

    seed(
        scan_dir=args.scan_dir,
        vector_dir=_DEFAULT_VECTOR_DIR,
        doc_type=args.doc_type,
        write=args.write,
        external_llm_context_allowed=external_llm_context_allowed,
        manifest_path=args.manifest,
        include_review_required=args.include_review_required,
    )


if __name__ == "__main__":
    main()
