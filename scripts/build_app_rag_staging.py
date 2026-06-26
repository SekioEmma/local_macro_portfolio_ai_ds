#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OFFICIAL_SOURCE_KINDS = frozenset({"central_bank_policy", "official_release", "official_outlook"})
INSTITUTIONAL_SOURCE_KIND = "institutional_research"
DEFAULT_MANIFEST_NAME = "app_full_manifest.jsonl"
DEFAULT_AUDIT_NAME = "app_full_merge_audit.json"


@dataclass(frozen=True)
class MergeSource:
    root: Path
    row: dict[str, Any]
    source_output_relpath: str | None


@dataclass(frozen=True)
class MergeResult:
    rows: list[MergeSource]
    audit: dict[str, Any]


def build_app_rag_staging(
    *,
    base_root: Path,
    base_manifest: Path,
    official_root: Path,
    official_manifest: Path,
    authorize_institutional_external_context: bool,
) -> MergeResult:
    base_rows = _load_rows(base_manifest)
    official_rows = _load_rows(official_manifest)
    merged: list[MergeSource] = []
    removed_base_official = 0
    authorized_institutional = 0

    for row in base_rows:
        if row.get("source_kind") == "official_release":
            removed_base_official += 1
            continue
        source_output_relpath = row.get("output_relpath") if isinstance(row.get("output_relpath"), str) else None
        staged = _with_evidence_tier(row)
        if staged.get("source_kind") == INSTITUTIONAL_SOURCE_KIND:
            if authorize_institutional_external_context:
                staged = _authorize_institutional_view(staged)
                authorized_institutional += 1
            else:
                staged = dict(staged)
                staged.setdefault("evidence_tier", "institutional_view")
                staged.setdefault("is_official_source", False)
        merged.append(MergeSource(base_root, staged, source_output_relpath))

    for row in official_rows:
        staged = _with_evidence_tier(row)
        source_output_relpath = staged.get("output_relpath") if isinstance(staged.get("output_relpath"), str) else None
        merged.append(MergeSource(official_root, staged, source_output_relpath))

    rows = [item.row for item in merged]
    audit = {
        "base_documents": len(base_rows),
        "official_release_documents": len(official_rows),
        "removed_base_official_release_rows": removed_base_official,
        "authorized_institutional_research_rows": authorized_institutional,
        "merged_documents": len(rows),
        "cohort_counts": _count_field(rows, "cohort"),
        "runtime_doc_type_counts": _count_field(rows, "runtime_doc_type"),
        "evidence_tier_counts": _count_field(rows, "evidence_tier"),
        "is_official_source_counts": _count_field(rows, "is_official_source"),
        "duplicate_document_ids": sorted(_duplicate_document_ids(rows)),
    }
    return MergeResult(merged, audit)


def write_merge_result(result: MergeResult, output_root: Path, *, force: bool = False) -> None:
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()) and not force:
        raise FileExistsError(f"output root is not empty: {output_root}")
    metadata_dir = output_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    for item in result.rows:
        output_relpath = item.row.get("output_relpath")
        if not isinstance(output_relpath, str) or not output_relpath.strip():
            continue
        source_relpath = item.source_output_relpath
        if not isinstance(source_relpath, str) or not source_relpath.strip():
            continue
        source_path = (item.root / _safe_relpath(source_relpath)).resolve()
        if not source_path.is_relative_to(item.root.resolve()):
            raise ValueError("source output path escapes source root")
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        target_path = (output_root / _safe_relpath(output_relpath)).resolve()
        if not target_path.is_relative_to(output_root):
            raise ValueError("target output path escapes output root")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    manifest_path = metadata_dir / DEFAULT_MANIFEST_NAME
    manifest_path.write_text(
        "\n".join(json.dumps(item.row, ensure_ascii=False, sort_keys=True) for item in result.rows) + "\n",
        encoding="utf-8",
    )
    audit_path = metadata_dir / DEFAULT_AUDIT_NAME
    audit_path.write_text(
        json.dumps(result.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError(f"manifest row is not an object: {path}")
            rows.append(parsed)
    return rows


def _with_evidence_tier(row: dict[str, Any]) -> dict[str, Any]:
    staged = dict(row)
    source_kind = staged.get("source_kind")
    if source_kind in OFFICIAL_SOURCE_KINDS:
        staged["evidence_tier"] = "official_evidence"
        staged["is_official_source"] = True
    elif source_kind == INSTITUTIONAL_SOURCE_KIND:
        staged["evidence_tier"] = "institutional_view"
        staged["is_official_source"] = False
    return staged


def _authorize_institutional_view(row: dict[str, Any]) -> dict[str, Any]:
    staged = dict(row)
    output_relpath = staged.get("output_relpath")
    if isinstance(output_relpath, str) and output_relpath.strip():
        old_relpath = _safe_relpath(output_relpath)
        staged["output_relpath"] = str(Path("research_report") / old_relpath.name).replace("\\", "/")
    staged["cohort"] = "research_report"
    staged["runtime_doc_type"] = "research_report"
    staged["candidate_doc_type"] = "research_report"
    staged["source_kind"] = INSTITUTIONAL_SOURCE_KIND
    staged["evidence_tier"] = "institutional_view"
    staged["is_official_source"] = False
    staged["external_llm_context_allowed"] = True
    staged["allowed_use"] = "external_context_candidate"
    staged["ingest_status"] = "eligible"
    staged["rights_status"] = "user_authorized_external_context"
    staged["external_context_authorized_by_user"] = True
    staged["authorization_basis"] = "user_authorized_institutional_research_for_ds_context"
    return staged


def _safe_relpath(value: str) -> Path:
    relpath = Path(value)
    if relpath.is_absolute() or ".." in relpath.parts:
        raise ValueError(f"unsafe output_relpath: {value}")
    return relpath


def _duplicate_document_ids(rows: list[dict[str, Any]]) -> set[str]:
    counts = Counter(row.get("document_id") for row in rows if isinstance(row.get("document_id"), str))
    return {doc_id for doc_id, count in counts.items() if count > 1}


def _count_field(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row.get(field)) for row in rows)
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a merged governed app RAG staging directory.")
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--official-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--authorize-institutional-external-context", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        result = build_app_rag_staging(
            base_root=args.base_root.resolve(),
            base_manifest=args.base_manifest.resolve(),
            official_root=args.official_root.resolve(),
            official_manifest=args.official_manifest.resolve(),
            authorize_institutional_external_context=args.authorize_institutional_external_context,
        )
        payload = dict(result.audit)
        payload["output_root"] = str(args.output_root.resolve())
        payload["manifest"] = str((args.output_root / "metadata" / DEFAULT_MANIFEST_NAME).resolve())
        payload["dry_run"] = args.dry_run
        if not args.dry_run:
            write_merge_result(result, args.output_root, force=args.force)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
