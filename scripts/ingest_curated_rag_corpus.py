#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_backend.services.curated_rag_ingest import (  # noqa: E402
    DEFAULT_VECTOR_ROOT,
    CuratedRAGIngestError,
    ingest_curated_corpus,
    summarize_result,
)
from llm.embedding_service import OfflineEmbeddingModelNotAvailable  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed ingest for macro-rag-corpus-curator staging output.")
    parser.add_argument("--curated-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vector-root", type=Path, default=DEFAULT_VECTOR_ROOT)
    parser.add_argument("--vector-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--offline-only", action="store_true", default=True)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Prune existing vector/chunk documents absent from the accepted full manifest before writing.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    vector_root = args.vector_dir or args.vector_root
    try:
        result = ingest_curated_corpus(
            curated_root=args.curated_root,
            manifest_path=args.manifest,
            vector_root=vector_root,
            write=args.write,
            offline_only=args.offline_only,
            strict=args.strict,
            replace_existing=args.replace_existing,
        )
    except (CuratedRAGIngestError, FileNotFoundError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    except OfflineEmbeddingModelNotAvailable as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2

    payload = summarize_result(result)
    payload["status"] = "ok"
    if result.plan.accepted_document_count == 0:
        payload["status"] = "blocked_no_eligible_documents"
    elif result.mode == "blocked-rejected-records":
        payload["status"] = "blocked_rejected_manifest_records"
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload["status"] != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
