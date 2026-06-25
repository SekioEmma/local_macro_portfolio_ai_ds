#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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
FEDERAL_RESERVE_DOMAIN = "federalreserve.gov"
FOMC_ID_PREFIX_MATERIAL_TYPES = {
    "fomc_statement_": "statement",
    "fomc_minutes_": "minutes",
    "fomc_projection_": "sep",
    "fomc_implementation_": "implementation_note",
    "fomc_longer_": "longer_run_goals",
}
HARD_ERROR_REASONS = frozenset(
    {
        "duplicate_document_id",
        "hash_or_identity_mutation_attempt",
        "url_domain_mismatch",
    }
)


@dataclass(frozen=True)
class AdmissionDecision:
    document_id: str | None
    status: str
    reason: str
    fields: tuple[str, ...]
    hard_error: bool = False


@dataclass(frozen=True)
class AdmissionResult:
    derived_rows: list[dict[str, Any]]
    audit: dict[str, Any]
    has_hard_errors: bool


def build_verified_manifest(
    *,
    manifest_path: Path,
    overrides_path: Path | None = None,
    source_ledger_path: Path,
) -> AdmissionResult:
    manifest_rows = _read_jsonl(manifest_path)
    override_rows = _read_jsonl(overrides_path) if overrides_path is not None else []
    ledger_rows = _read_jsonl(source_ledger_path)

    manifest_counts = _document_id_counts(manifest_rows)
    duplicate_manifest_ids = {doc_id for doc_id, count in manifest_counts.items() if count > 1}
    ledger_counts = _document_id_counts(ledger_rows)
    duplicate_ledger_ids = {doc_id for doc_id, count in ledger_counts.items() if count > 1}

    overrides_by_doc_id, override_decisions = _index_overrides(override_rows)
    ledgers_by_doc_id = {
        row["document_id"]: row
        for row in ledger_rows
        if isinstance(row.get("document_id"), str) and row["document_id"] not in duplicate_ledger_ids
    }

    decisions: list[AdmissionDecision] = []
    derived_rows: list[dict[str, Any]] = []
    for row in manifest_rows:
        derived, decision = _derive_manifest_row(
            row=row,
            duplicate_manifest_ids=duplicate_manifest_ids,
            duplicate_ledger_ids=duplicate_ledger_ids,
            ledgers_by_doc_id=ledgers_by_doc_id,
            overrides_by_doc_id=overrides_by_doc_id,
        )
        derived_rows.append(derived)
        decisions.append(decision)

    all_decisions = decisions + override_decisions
    audit = _build_audit(
        source_documents=len(manifest_rows),
        derived_documents=len(derived_rows),
        override_rows=len(override_rows),
        source_ledger_rows=len(ledger_rows),
        source_ledger_verified_rows=sum(
            1 for row in ledger_rows if row.get("verification_status") == "verified"
        ),
        decisions=decisions,
        override_decisions=override_decisions,
    )
    return AdmissionResult(
        derived_rows=derived_rows,
        audit=audit,
        has_hard_errors=any(decision.hard_error for decision in all_decisions),
    )


def write_outputs(result: AdmissionResult, *, output_manifest: Path, audit_report: Path) -> None:
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


def _document_id_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        row.get("document_id")
        for row in rows
        if isinstance(row.get("document_id"), str) and row.get("document_id")
    )


def _index_overrides(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[AdmissionDecision]]:
    counts = _document_id_counts(rows)
    duplicate_ids = {doc_id for doc_id, count in counts.items() if count > 1}
    indexed: dict[str, dict[str, Any]] = {}
    decisions: list[AdmissionDecision] = []
    for row in rows:
        doc_id = row.get("document_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            decisions.append(
                _decision(None, "unchanged", "missing_source_ledger", ("document_id",), hard_error=True)
            )
            continue
        if doc_id in duplicate_ids:
            decisions.append(
                _decision(doc_id, "unchanged", "duplicate_document_id", ("document_id",), hard_error=True)
            )
            continue
        indexed[doc_id] = row
    return indexed, decisions


def _derive_manifest_row(
    *,
    row: dict[str, Any],
    duplicate_manifest_ids: set[str],
    duplicate_ledger_ids: set[str],
    ledgers_by_doc_id: dict[str, dict[str, Any]],
    overrides_by_doc_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], AdmissionDecision]:
    doc_id = row.get("document_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        return _unchanged(row, None, "duplicate_document_id", ("document_id",), hard_error=True)
    if doc_id in duplicate_manifest_ids or doc_id in duplicate_ledger_ids:
        return _unchanged(row, doc_id, "duplicate_document_id", ("document_id",), hard_error=True)

    ledger = ledgers_by_doc_id.get(doc_id)
    override = overrides_by_doc_id.get(doc_id)
    if ledger is None:
        return _unchanged(row, doc_id, "missing_source_ledger", ("source_ledger",))

    mutation_fields = _identity_mutation_fields(row, ledger, override)
    if mutation_fields:
        return _unchanged(
            row,
            doc_id,
            "hash_or_identity_mutation_attempt",
            mutation_fields,
            hard_error=True,
        )

    proposed_url = _coalesce_text(override.get("canonical_url") if override else None, ledger.get("canonical_url"))
    proposed_domain = _coalesce_text(override.get("source_domain") if override else None, ledger.get("source_domain"))
    if not _override_matches_ledger(override, ledger):
        return _unchanged(
            row,
            doc_id,
            "url_domain_mismatch",
            ("canonical_url", "source_domain"),
            hard_error=True,
        )

    reason, fields, hard_error = _admission_rejection(row, ledger, proposed_url, proposed_domain)
    if reason is not None:
        return _unchanged(row, doc_id, reason, fields, hard_error=hard_error)

    derived = dict(row)
    if proposed_url is not None:
        derived["canonical_url"] = proposed_url
        derived["source_domain"] = proposed_domain
    elif "canonical_url" not in derived:
        derived["canonical_url"] = None
    if proposed_domain is None and "source_domain" not in derived:
        derived["source_domain"] = None
    derived["provenance_status"] = "verified"
    derived["ingest_status"] = "eligible"
    derived["fomc_material_type"] = _material_type(row, ledger)
    derived["admission_source"] = "source_ledger"
    derived["admission_status"] = "verified"
    derived["admission_reason"] = "verified_fomc_policy_doc"
    derived["verified_by"] = ledger.get("verified_by")
    derived["verification_basis"] = ledger.get("verification_basis")
    return derived, _decision(
        doc_id,
        "verified",
        "verified_fomc_policy_doc",
        (
            "provenance_status",
            "ingest_status",
            "fomc_material_type",
            "admission_status",
        ),
    )


def _admission_rejection(
    row: dict[str, Any],
    ledger: dict[str, Any],
    proposed_url: str | None,
    proposed_domain: str | None,
) -> tuple[str | None, tuple[str, ...], bool]:
    if ledger.get("verification_status") != "verified":
        return "ledger_not_verified", ("verification_status",), False
    if ledger.get("verified_by") != "user" or not _coalesce_text(ledger.get("verification_basis")):
        return "ledger_not_verified", ("verified_by", "verification_basis"), False
    if ledger.get("publisher") != FEDERAL_RESERVE_PUBLISHER:
        return "non_federalreserve_domain", ("publisher",), False
    if proposed_url is not None or proposed_domain is not None:
        if proposed_domain != FEDERAL_RESERVE_DOMAIN or ledger.get("source_domain") != FEDERAL_RESERVE_DOMAIN:
            return "non_federalreserve_domain", ("source_domain",), False
        url_reason, url_host = _validate_canonical_url(proposed_url)
        if url_reason is not None or url_host != proposed_domain:
            return "url_domain_mismatch", ("canonical_url", "source_domain"), True
    elif not _has_verified_local_source(row, ledger):
        return "missing_source_ledger", ("source_relpath", "verification_basis"), False

    material_type = _material_type(row, ledger)
    if material_type not in ALLOWED_FOMC_MATERIAL_TYPES or not str(row.get("document_id", "")).startswith("fomc_"):
        return "unsupported_material_type", ("material_type",), False
    if ledger.get("document_type") != "policy_doc" or row.get("runtime_doc_type") != "policy_doc":
        return "not_policy_doc", ("document_type", "runtime_doc_type"), False
    if row.get("extraction_status") != "ready":
        return "extraction_not_ready", ("extraction_status",), False
    if row.get("external_llm_context_allowed") is not True or row.get("local_only") is True:
        return "external_llm_not_allowed", ("external_llm_context_allowed", "local_only"), False
    if row.get("pending_governance") is True:
        return "not_policy_doc", ("pending_governance",), False
    return None, (), False


def _has_verified_local_source(row: dict[str, Any], ledger: dict[str, Any]) -> bool:
    if ledger.get("verification_basis") != "user_curated_local_file":
        return False
    manifest_relpath = row.get("source_relpath")
    ledger_relpath = ledger.get("source_relpath")
    if not isinstance(manifest_relpath, str) or not manifest_relpath.strip():
        return False
    if not isinstance(ledger_relpath, str) or ledger_relpath != manifest_relpath:
        return False
    return isinstance(row.get("source_file_sha256"), str) and bool(row["source_file_sha256"])


def _validate_canonical_url(value: object) -> tuple[str | None, str]:
    if not isinstance(value, str) or not value.strip():
        return "url_domain_mismatch", ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        return "url_domain_mismatch", ""
    return None, parsed.hostname.lower().strip(".")


def _override_matches_ledger(override: dict[str, Any] | None, ledger: dict[str, Any]) -> bool:
    if override is None:
        return True
    canonical_url = override.get("canonical_url")
    source_domain = override.get("source_domain")
    if canonical_url is not None and canonical_url != ledger.get("canonical_url"):
        return False
    if source_domain is not None and source_domain != ledger.get("source_domain"):
        return False
    return True


def _identity_mutation_fields(
    row: dict[str, Any],
    ledger: dict[str, Any],
    override: dict[str, Any] | None,
) -> tuple[str, ...]:
    fields: set[str] = set()
    original_hash = row.get("cleaned_content_sha256")
    for candidate in (ledger, override or {}):
        if "document_id" in candidate and candidate.get("document_id") != row.get("document_id"):
            fields.add("document_id")
        if "cleaned_content_sha256" in candidate and candidate.get("cleaned_content_sha256") != original_hash:
            fields.add("cleaned_content_sha256")
    return tuple(sorted(fields))


def _material_type(row: dict[str, Any], ledger: dict[str, Any]) -> str | None:
    value = (
        row.get("fomc_material_type")
        or row.get("material_type")
        or ledger.get("fomc_material_type")
        or ledger.get("material_type")
    )
    if isinstance(value, str):
        return value
    document_id = row.get("document_id")
    if not isinstance(document_id, str):
        return None
    for prefix, material_type in FOMC_ID_PREFIX_MATERIAL_TYPES.items():
        if document_id.startswith(prefix):
            return material_type
    return None


def _coalesce_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _unchanged(
    row: dict[str, Any],
    document_id: str | None,
    reason: str,
    fields: tuple[str, ...],
    *,
    hard_error: bool = False,
) -> tuple[dict[str, Any], AdmissionDecision]:
    derived = dict(row)
    derived["admission_source"] = "source_ledger" if reason != "missing_source_ledger" else "none"
    derived["admission_status"] = "unchanged"
    derived["admission_reason"] = reason
    if isinstance(document_id, str):
        derived["verified_by"] = None
        derived["verification_basis"] = None
    return derived, _decision(document_id, "unchanged", reason, fields, hard_error=hard_error)


def _decision(
    document_id: str | None,
    status: str,
    reason: str,
    fields: tuple[str, ...],
    *,
    hard_error: bool = False,
) -> AdmissionDecision:
    return AdmissionDecision(
        document_id=document_id,
        status=status,
        reason=reason,
        fields=tuple(sorted(fields)),
        hard_error=hard_error,
    )


def _build_audit(
    *,
    source_documents: int,
    derived_documents: int,
    override_rows: int,
    source_ledger_rows: int,
    source_ledger_verified_rows: int,
    decisions: list[AdmissionDecision],
    override_decisions: list[AdmissionDecision],
) -> dict[str, Any]:
    promoted = [decision for decision in decisions if decision.status == "verified"]
    unchanged = [decision for decision in decisions if decision.status == "unchanged"]
    rejection_counts = Counter(
        decision.reason
        for decision in decisions + override_decisions
        if decision.status == "unchanged" and decision.reason
    )
    return {
        "summary": {
            "source_documents": source_documents,
            "source_ledger_rows": source_ledger_rows,
            "source_ledger_verified_rows": source_ledger_verified_rows,
            "override_rows": override_rows,
            "promoted_documents": len(promoted),
            "unchanged_documents": len(unchanged),
            "hold_documents": sum(1 for decision in unchanged if decision.reason != "duplicate_document_id"),
            "derived_documents": derived_documents,
            "hard_error_count": sum(
                1 for decision in decisions + override_decisions if decision.hard_error
            ),
            "rejection_reason_counts": dict(sorted(rejection_counts.items())),
        },
        "admission_results": [_decision_to_json(decision) for decision in decisions],
        "override_results": [_decision_to_json(decision) for decision in override_decisions],
    }


def _decision_to_json(decision: AdmissionDecision) -> dict[str, Any]:
    return {
        "document_id": decision.document_id,
        "status": decision.status,
        "reason": decision.reason,
        "fields": list(decision.fields),
        "hard_error": decision.hard_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a source-ledger-verified derived RAG manifest.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    protected_inputs = {
        args.manifest.resolve(),
        args.source_ledger.resolve(),
    }
    if args.overrides is not None:
        protected_inputs.add(args.overrides.resolve())
    if args.output_manifest.resolve() in protected_inputs or args.audit_report.resolve() in protected_inputs:
        print(json.dumps({"status": "blocked", "reason": "outputs_must_not_replace_inputs"}))
        return 2

    result = build_verified_manifest(
        manifest_path=args.manifest,
        overrides_path=args.overrides,
        source_ledger_path=args.source_ledger,
    )
    if args.dry_run:
        print(json.dumps(result.audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if args.strict and result.has_hard_errors else 0

    if args.strict and result.has_hard_errors:
        print(json.dumps(result.audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    write_outputs(result, output_manifest=args.output_manifest, audit_report=args.audit_report)
    print(json.dumps(result.audit["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
