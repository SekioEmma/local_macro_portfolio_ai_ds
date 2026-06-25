#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ALLOWED_FOMC_MATERIAL_TYPES = frozenset(
    {
        "statement",
        "minutes",
        "sep",
        "implementation_note",
        "longer_run_goals",
    }
)
FEDERAL_RESERVE_PUBLISHER = "Board of Governors of the Federal Reserve System"
FOMC_ID_PREFIX_MATERIAL_TYPES = {
    "fomc_statement_": "statement",
    "fomc_minutes_": "minutes",
    "fomc_projection_": "sep",
    "fomc_implementation_": "implementation_note",
    "fomc_longer_": "longer_run_goals",
}


def build_template_rows(manifest_path: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(manifest_path)
    candidates = [_template_row(row) for row in rows if _is_fomc_candidate(row)]
    return sorted(candidates, key=lambda row: row["document_id"])


def write_template(rows: list[dict[str, Any]], output_path: Path, *, force: bool = False) -> None:
    if output_path.exists() and not force:
        raise FileExistsError(f"refusing_to_overwrite_existing_template: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def summarize_template(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_documents": len(rows),
        "material_type_counts": dict(sorted(Counter(row.get("material_type") for row in rows).items())),
        "verification_status_counts": dict(
            sorted(Counter(row.get("verification_status") for row in rows).items())
        ),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = {"__invalid_json_line__": line_no}
        rows.append(row if isinstance(row, dict) else {"__invalid_json_line__": line_no})
    return rows


def _is_fomc_candidate(row: dict[str, Any]) -> bool:
    return (
        row.get("source_kind") == "central_bank_policy"
        and row.get("runtime_doc_type") == "policy_doc"
        and _material_type(row) in ALLOWED_FOMC_MATERIAL_TYPES
        and isinstance(row.get("document_id"), str)
        and bool(row["document_id"].strip())
    )


def _template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row["document_id"],
        "source_relpath": _copy_or_null(row.get("source_relpath")),
        "source_file_sha256": _copy_or_null(row.get("source_file_sha256")),
        "canonical_url": None,
        "source_domain": None,
        "publisher": FEDERAL_RESERVE_PUBLISHER,
        "source_kind": "central_bank_policy",
        "document_type": "policy_doc",
        "material_type": _material_type(row),
        "publication_date": _copy_or_null(row.get("publication_date") or row.get("release_date")),
        "verification_status": "pending_user_verification",
        "verified_by": None,
        "verification_basis": None,
    }


def _material_type(row: dict[str, Any]) -> str | None:
    value = row.get("fomc_material_type") or row.get("material_type")
    if isinstance(value, str):
        return value
    document_id = row.get("document_id")
    if not isinstance(document_id, str):
        return None
    for prefix, material_type in FOMC_ID_PREFIX_MATERIAL_TYPES.items():
        if document_id.startswith(prefix):
            return material_type
    return None


def _copy_or_null(value: object) -> object:
    if isinstance(value, str) and value.strip():
        return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a pending user-verification FOMC source ledger template.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    rows = build_template_rows(args.manifest)
    summary = summarize_template(rows)
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    write_template(rows, args.output_ledger, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
