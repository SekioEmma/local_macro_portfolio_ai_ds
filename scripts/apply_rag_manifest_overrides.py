#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ALLOWED_OVERRIDE_FIELDS = frozenset({"document_id", "canonical_url", "source_domain"})
PROVENANCE_FLAG = "metadata_override_applied"


@dataclass(frozen=True)
class OverrideDecision:
    document_id: str | None
    status: str
    reason: str | None
    fields: tuple[str, ...]


@dataclass(frozen=True)
class RemediationResult:
    derived_rows: list[dict[str, Any]]
    audit: dict[str, Any]
    has_errors: bool


def apply_overrides(
    *,
    manifest_path: Path,
    overrides_path: Path,
) -> RemediationResult:
    manifest_rows = _read_jsonl(manifest_path)
    override_rows = _read_jsonl(overrides_path)

    manifest_doc_counts = Counter(
        row.get("document_id")
        for row in manifest_rows
        if isinstance(row, dict) and isinstance(row.get("document_id"), str) and row.get("document_id")
    )
    duplicate_manifest_ids = {doc_id for doc_id, count in manifest_doc_counts.items() if count > 1}
    valid_manifest_ids = {doc_id for doc_id, count in manifest_doc_counts.items() if count == 1}

    manifest_decisions = _audit_manifest_records(manifest_rows, duplicate_manifest_ids)
    override_duplicate_ids = _duplicate_override_document_ids(override_rows)
    duplicate_urls = _duplicate_canonical_urls(override_rows)

    accepted_by_doc_id: dict[str, dict[str, str]] = {}
    override_decisions: list[OverrideDecision] = []
    for row in override_rows:
        decision, clean_override = _validate_override(
            row=row,
            valid_manifest_ids=valid_manifest_ids,
            duplicate_manifest_ids=duplicate_manifest_ids,
            override_duplicate_ids=override_duplicate_ids,
            duplicate_urls=duplicate_urls,
            manifest_rows=manifest_rows,
        )
        override_decisions.append(decision)
        if clean_override is not None:
            accepted_by_doc_id[clean_override["document_id"]] = clean_override

    derived_rows = [_derive_row(row, accepted_by_doc_id) for row in manifest_rows]
    audit = _build_audit(
        source_documents=len(manifest_rows),
        derived_documents=len(derived_rows),
        override_rows=len(override_rows),
        manifest_decisions=manifest_decisions,
        override_decisions=override_decisions,
        unchanged_documents=sum(
            1
            for row in manifest_rows
            if not isinstance(row, dict) or row.get("document_id") not in accepted_by_doc_id
        ),
    )
    has_errors = bool(audit["summary"]["rejection_reason_counts"])
    return RemediationResult(derived_rows=derived_rows, audit=audit, has_errors=has_errors)


def write_outputs(result: RemediationResult, *, output_manifest: Path, audit_report: Path) -> None:
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    audit_report.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in result.derived_rows) + "\n",
        encoding="utf-8",
    )
    audit_report.write_text(
        json.dumps(result.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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


def _audit_manifest_records(
    rows: list[dict[str, Any]],
    duplicate_manifest_ids: set[str],
) -> list[OverrideDecision]:
    decisions: list[OverrideDecision] = []
    for row in rows:
        doc_id = row.get("document_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            decisions.append(OverrideDecision(None, "rejected", "manifest_record_invalid", ("document_id",)))
        elif doc_id in duplicate_manifest_ids:
            decisions.append(OverrideDecision(doc_id, "rejected", "duplicate_manifest_document_id", ("document_id",)))
    return decisions


def _duplicate_override_document_ids(rows: list[dict[str, Any]]) -> set[str]:
    counts = Counter(row.get("document_id") for row in rows if isinstance(row.get("document_id"), str))
    return {doc_id for doc_id, count in counts.items() if count > 1}


def _duplicate_canonical_urls(rows: list[dict[str, Any]]) -> set[str]:
    seen: dict[str, str] = {}
    duplicated: set[str] = set()
    for row in rows:
        doc_id = row.get("document_id")
        canonical_url = row.get("canonical_url")
        if not isinstance(doc_id, str) or not isinstance(canonical_url, str):
            continue
        existing_doc = seen.get(canonical_url)
        if existing_doc is not None and existing_doc != doc_id:
            duplicated.add(canonical_url)
        else:
            seen[canonical_url] = doc_id
    return duplicated


def _validate_override(
    *,
    row: dict[str, Any],
    valid_manifest_ids: set[str],
    duplicate_manifest_ids: set[str],
    override_duplicate_ids: set[str],
    duplicate_urls: set[str],
    manifest_rows: list[dict[str, Any]],
) -> tuple[OverrideDecision, dict[str, str] | None]:
    unknown_fields = tuple(sorted(set(row) - ALLOWED_OVERRIDE_FIELDS))
    doc_id = row.get("document_id")
    if unknown_fields:
        return _reject(_safe_doc_id(doc_id), "unknown_override_field", unknown_fields), None
    if not isinstance(doc_id, str) or not doc_id.strip():
        return _reject(None, "missing_document_id", ("document_id",)), None
    if doc_id in override_duplicate_ids:
        return _reject(doc_id, "duplicate_override_document_id", ("document_id",)), None
    if doc_id in duplicate_manifest_ids:
        return _reject(doc_id, "duplicate_manifest_document_id", ("document_id",)), None
    if doc_id not in valid_manifest_ids:
        return _reject(doc_id, "unknown_document_id", ("document_id",)), None

    canonical_url = row.get("canonical_url")
    source_domain = row.get("source_domain")
    if canonical_url in duplicate_urls:
        return _reject(doc_id, "duplicate_canonical_url", ("canonical_url",)), None
    if not isinstance(source_domain, str) or not source_domain.strip():
        return _reject(doc_id, "missing_source_domain", ("source_domain",)), None

    normalized_domain = _normalize_domain(source_domain)
    url_status, url_host = _validate_canonical_url(canonical_url)
    if url_status is not None:
        return _reject(doc_id, url_status, ("canonical_url",)), None
    if url_host != normalized_domain:
        return _reject(doc_id, "source_domain_host_mismatch", ("canonical_url", "source_domain")), None

    manifest_row = next(row for row in manifest_rows if row.get("document_id") == doc_id)
    existing_domain = manifest_row.get("source_domain")
    if isinstance(existing_domain, str) and existing_domain.strip():
        if _normalize_domain(existing_domain) != normalized_domain:
            return _reject(doc_id, "source_domain_conflicts_with_manifest", ("source_domain",)), None
    existing_url = manifest_row.get("canonical_url")
    if isinstance(existing_url, str) and existing_url.strip():
        return _reject(doc_id, "canonical_url_already_present", ("canonical_url",)), None

    return (
        OverrideDecision(doc_id, "accepted", None, ("canonical_url", "source_domain")),
        {
            "document_id": doc_id,
            "canonical_url": canonical_url,
            "source_domain": normalized_domain,
        },
    )


def _reject(document_id: str | None, reason: str, fields: tuple[str, ...]) -> OverrideDecision:
    return OverrideDecision(document_id, "rejected", reason, tuple(sorted(fields)))


def _safe_doc_id(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _validate_canonical_url(value: object) -> tuple[str | None, str]:
    if not isinstance(value, str) or not value.strip():
        return "invalid_canonical_url", ""
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return "non_https_url", ""
    if parsed.username or parsed.password or not parsed.hostname:
        return "invalid_canonical_url", ""
    return None, parsed.hostname.lower().strip(".")


def _normalize_domain(value: str) -> str:
    domain = value.strip().lower().strip(".")
    if "/" in domain or "@" in domain or ":" in domain or not domain:
        return ""
    return domain


def _derive_row(row: dict[str, Any], accepted_by_doc_id: dict[str, dict[str, str]]) -> dict[str, Any]:
    doc_id = row.get("document_id")
    if not isinstance(doc_id, str) or doc_id not in accepted_by_doc_id:
        return dict(row)
    override = accepted_by_doc_id[doc_id]
    derived = dict(row)
    derived["canonical_url"] = override["canonical_url"]
    derived["source_domain"] = override["source_domain"]
    derived[PROVENANCE_FLAG] = True
    return derived


def _build_audit(
    *,
    source_documents: int,
    derived_documents: int,
    override_rows: int,
    manifest_decisions: list[OverrideDecision],
    override_decisions: list[OverrideDecision],
    unchanged_documents: int,
) -> dict[str, Any]:
    accepted = [decision for decision in override_decisions if decision.status == "accepted"]
    rejected = [decision for decision in override_decisions if decision.status == "rejected"]
    all_rejections = rejected + [decision for decision in manifest_decisions if decision.status == "rejected"]
    reason_counts = Counter(decision.reason for decision in all_rejections if decision.reason)
    return {
        "summary": {
            "source_documents": source_documents,
            "override_rows": override_rows,
            "accepted_overrides": len(accepted),
            "rejected_overrides": len(rejected),
            "skipped_overrides": 0,
            "unchanged_documents": unchanged_documents,
            "derived_documents": derived_documents,
            "rejection_reason_counts": dict(sorted(reason_counts.items())),
        },
        "override_results": [_decision_to_json(decision) for decision in override_decisions],
        "manifest_results": [_decision_to_json(decision) for decision in manifest_decisions],
    }


def _decision_to_json(decision: OverrideDecision) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "document_id": decision.document_id,
        "status": decision.status,
        "fields": list(decision.fields),
    }
    if decision.reason is not None:
        payload["reason"] = decision.reason
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply audited canonical URL overrides to a RAG manifest.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if args.output_manifest.resolve() == args.manifest.resolve():
        print(json.dumps({"status": "blocked", "reason": "output_manifest_must_not_replace_source"}))
        return 2

    result = apply_overrides(manifest_path=args.manifest, overrides_path=args.overrides)
    if args.dry_run:
        print(json.dumps(result.audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if args.strict and result.has_errors else 0

    if args.strict and result.has_errors:
        print(json.dumps(result.audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    write_outputs(result, output_manifest=args.output_manifest, audit_report=args.audit_report)
    print(json.dumps(result.audit["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
