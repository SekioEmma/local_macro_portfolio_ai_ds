#!/usr/bin/env python3
"""Seed the RAG knowledge base from files the user has placed in data/knowledge_base/input/.

Usage:
    python scripts/seed_knowledge_base.py                  # dry-run: shows what would be indexed
    python scripts/seed_knowledge_base.py --write          # write chunk text store + vector store
    python scripts/seed_knowledge_base.py --doc-type research_report  # override doc_type
    python scripts/seed_knowledge_base.py --scan-dir /path/to/files   # custom input dir

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llm.document_chunker import chunk_text
from llm.chunk_text_store import ChunkTextStore, StoredChunk

_DEFAULT_INPUT_DIR = ROOT / "data" / "knowledge_base" / "input"
_DEFAULT_VECTOR_DIR = ROOT / "data" / "vector_store"
_CHUNK_TEXT_DB = _DEFAULT_VECTOR_DIR / "chunks.sqlite"
_VALID_DOC_TYPES = {"policy_doc", "research_report", "historical_data", "one_shot_news"}
_EXTENSIONS = {".txt", ".md"}


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


def seed(
    *,
    scan_dir: Path,
    vector_dir: Path,
    doc_type: str,
    write: bool,
    verbose: bool = True,
) -> dict[str, int]:
    if doc_type not in _VALID_DOC_TYPES:
        raise ValueError(f"doc_type must be one of {sorted(_VALID_DOC_TYPES)}, got {doc_type!r}")

    files = sorted(p for p in scan_dir.iterdir() if p.suffix in _EXTENSIONS) if scan_dir.exists() else []

    if not files:
        if verbose:
            print(f"No .txt/.md files found in {scan_dir}")
        return {"files": 0, "chunks": 0, "written": 0}

    chunk_store = ChunkTextStore(_CHUNK_TEXT_DB) if write else None

    if write:
        try:
            from llm.vector_store import VectorStore
            from llm.embedding_service import EmbeddingService
            vs = VectorStore(vector_dir)
            emb_svc = EmbeddingService()
        except ImportError as exc:
            print(f"[error] Missing dependency: {exc}")
            print("Install with: pip install sentence-transformers chromadb")
            sys.exit(1)
    else:
        vs = None
        emb_svc = None

    total_chunks = 0
    total_written = 0

    for fpath in files:
        text = fpath.read_text(encoding="utf-8", errors="replace")
        doc_id = _doc_id_for_file(fpath)
        title = _title_from_file(fpath, text)
        source_domain = _source_domain_for(fpath)
        chunks = chunk_text(text, doc_id=doc_id)
        total_chunks += len(chunks)

        if verbose:
            print(f"  {'[dry-run]' if not write else '[write]'} {fpath.name} → {len(chunks)} chunks  doc_id={doc_id}")

        if write and chunk_store is not None and vs is not None and emb_svc is not None:
            texts = [c.text for c in chunks]
            embeddings = emb_svc.encode(texts)
            for chunk, embedding in zip(chunks, embeddings):
                stored = StoredChunk(
                    doc_id=chunk.doc_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    title=title,
                    doc_type=doc_type,
                    source_domain=source_domain,
                )
                chunk_store.upsert_chunk(stored)
                vs.upsert(
                    doc_id=chunk.doc_id,
                    chunk_index=chunk.chunk_index,
                    embedding=embedding,
                    metadata={"title": title, "doc_type": doc_type, "source_domain": source_domain},
                )
                total_written += 1

    if verbose:
        print(f"\nSummary: {len(files)} file(s), {total_chunks} chunk(s), {total_written} written.")
        if not write:
            print("Run with --write to actually index.")

    return {"files": len(files), "chunks": total_chunks, "written": total_written}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="Write chunks to vector store (default: dry-run)")
    parser.add_argument("--doc-type", default="research_report", help="Document type for all files in this run")
    parser.add_argument("--scan-dir", type=Path, default=_DEFAULT_INPUT_DIR, help="Directory to scan for .txt/.md files")
    args = parser.parse_args()

    print(f"Mode: {'WRITE' if args.write else 'DRY-RUN'}")
    print(f"Scanning: {args.scan_dir}")
    print(f"doc_type: {args.doc_type}\n")

    seed(
        scan_dir=args.scan_dir,
        vector_dir=_DEFAULT_VECTOR_DIR,
        doc_type=args.doc_type,
        write=args.write,
    )


if __name__ == "__main__":
    main()
