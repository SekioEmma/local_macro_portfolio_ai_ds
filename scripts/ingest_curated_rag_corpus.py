#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_backend.services.curated_rag_ingest import (  # noqa: E402
    DEFAULT_VECTOR_DIR,
    CuratedRAGIngestError,
    ingest_curated_corpus,
    summarize_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed ingest for macro-rag-corpus-curator staging output.")
    parser.add_argument("--curated-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vector-dir", type=Path, default=DEFAULT_VECTOR_DIR)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    try:
        result = ingest_curated_corpus(
            curated_root=args.curated_root,
            manifest_path=args.manifest,
            vector_dir=args.vector_dir,
            write=args.write,
        )
    except CuratedRAGIngestError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2

    payload = summarize_plan(result.plan)
    payload.update({
        "mode": result.mode,
        "candidate_chunks": result.chunk_count,
        "written_chunks": result.written_chunk_count,
        "status": "ok",
    })
    if args.write and result.plan.accepted_document_count == 0:
        payload["status"] = "no_eligible_documents_no_write"
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

