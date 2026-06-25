from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_verified_rag_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_verified_rag_manifest", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_verified_rag_manifest"] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> bytes:
    payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path.read_bytes()


def _manifest_row(
    document_id: str = "fomc_statement_2026_06_17",
    *,
    material_type: str = "statement",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "cleaned_content_sha256": "a" * 64,
        "candidate_doc_type": "policy_doc",
        "runtime_doc_type": "policy_doc",
        "external_llm_context_allowed": True,
        "local_only": False,
        "rights_status": "official_public",
        "source_kind": "central_bank_policy",
        "temporal_status": "as_released",
        "fomc_material_type": material_type,
        "extraction_status": "ready",
        "provenance_status": "partial",
        "ingest_status": "hold",
        "canonical_url": None,
        "source_domain": None,
        "source_relpath": "raw/path/that/must/not/appear.pdf",
        "body": "chunk text that must not appear in audit",
    }


def _ledger_row(
    document_id: str = "fomc_statement_2026_06_17",
    *,
    verification_status: str = "verified",
    canonical_url: str = "https://federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
    source_domain: str = "federalreserve.gov",
    document_type: str = "policy_doc",
    publisher: str = "Board of Governors of the Federal Reserve System",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "canonical_url": canonical_url,
        "source_domain": source_domain,
        "publisher": publisher,
        "source_kind": "central_bank_policy",
        "document_type": document_type,
        "publication_date": "2026-06-17",
        "verification_status": verification_status,
        "verified_by": "user",
        "verification_basis": "official_federalreserve_page_or_saved_metadata",
    }


def _override_row(
    document_id: str = "fomc_statement_2026_06_17",
    *,
    canonical_url: str = "https://federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
    source_domain: str = "federalreserve.gov",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "canonical_url": canonical_url,
        "source_domain": source_domain,
    }


def test_verified_fomc_statement_is_promoted_to_verified_eligible(tmp_path):
    result = _run_builder(tmp_path, [_manifest_row()], [_override_row()], [_ledger_row()])

    assert result.audit["summary"]["promoted_documents"] == 1
    derived = result.derived_rows[0]
    assert derived["provenance_status"] == "verified"
    assert derived["ingest_status"] == "eligible"
    assert derived["admission_status"] == "verified"
    assert derived["admission_source"] == "source_ledger"
    assert derived["verified_by"] == "user"
    assert derived["cleaned_content_sha256"] == "a" * 64


def test_missing_source_ledger_keeps_partial_hold(tmp_path):
    result = _run_builder(tmp_path, [_manifest_row()], [_override_row()], [])

    assert result.audit["summary"]["promoted_documents"] == 0
    assert result.audit["summary"]["rejection_reason_counts"] == {"missing_source_ledger": 1}
    derived = result.derived_rows[0]
    assert derived["provenance_status"] == "partial"
    assert derived["ingest_status"] == "hold"
    assert derived["admission_status"] == "unchanged"


def test_url_override_without_verified_ledger_does_not_promote(tmp_path):
    result = _run_builder(
        tmp_path,
        [_manifest_row()],
        [_override_row()],
        [_ledger_row(verification_status="pending")],
    )

    assert result.audit["summary"]["promoted_documents"] == 0
    assert result.audit["summary"]["rejection_reason_counts"] == {"ledger_not_verified": 1}
    assert result.derived_rows[0]["canonical_url"] is None
    assert result.derived_rows[0]["provenance_status"] == "partial"


def test_memo_bls_bea_and_weo_are_not_promoted(tmp_path):
    rows = [
        _manifest_row("memo_private_2026_06", material_type="memo"),
        _manifest_row("bls_cpi_2026_05", material_type="official_release"),
        _manifest_row("bea_gdp_2026_q1", material_type="official_release"),
        _manifest_row("imf_weo_2026_04", material_type="official_outlook"),
    ]
    ledgers = [_ledger_row(str(row["document_id"])) for row in rows]

    result = _run_builder(tmp_path, rows, [], ledgers)

    assert result.audit["summary"]["promoted_documents"] == 0
    assert result.audit["summary"]["rejection_reason_counts"] == {"unsupported_material_type": 4}
    assert {row["admission_status"] for row in result.derived_rows} == {"unchanged"}


def test_local_only_document_is_not_promoted(tmp_path):
    row = _manifest_row()
    row["local_only"] = True

    result = _run_builder(tmp_path, [row], [_override_row()], [_ledger_row()])

    assert result.audit["summary"]["rejection_reason_counts"] == {"external_llm_not_allowed": 1}
    assert result.derived_rows[0]["local_only"] is True
    assert result.derived_rows[0]["ingest_status"] == "hold"


def test_external_llm_context_false_document_is_not_promoted(tmp_path):
    row = _manifest_row()
    row["external_llm_context_allowed"] = False

    result = _run_builder(tmp_path, [row], [_override_row()], [_ledger_row()])

    assert result.audit["summary"]["rejection_reason_counts"] == {"external_llm_not_allowed": 1}
    assert result.derived_rows[0]["external_llm_context_allowed"] is False
    assert result.derived_rows[0]["provenance_status"] == "partial"


def test_source_domain_and_canonical_url_host_mismatch_is_rejected(tmp_path):
    result = _run_builder(
        tmp_path,
        [_manifest_row()],
        [
            _override_row(
                canonical_url="https://www.federalreserve.gov/newsevents/pressreleases/doc.htm",
                source_domain="federalreserve.gov",
            )
        ],
        [
            _ledger_row(
                canonical_url="https://www.federalreserve.gov/newsevents/pressreleases/doc.htm",
                source_domain="federalreserve.gov",
            )
        ],
    )

    assert result.audit["summary"]["rejection_reason_counts"] == {"url_domain_mismatch": 1}
    assert result.audit["summary"]["hard_error_count"] == 1
    assert result.derived_rows[0]["admission_status"] == "unchanged"


def test_cleaned_content_sha256_mutation_attempt_is_rejected(tmp_path):
    ledger = _ledger_row()
    ledger["cleaned_content_sha256"] = "b" * 64

    result = _run_builder(tmp_path, [_manifest_row()], [_override_row()], [ledger])

    assert result.audit["summary"]["rejection_reason_counts"] == {"hash_or_identity_mutation_attempt": 1}
    assert result.audit["summary"]["hard_error_count"] == 1
    assert result.derived_rows[0]["cleaned_content_sha256"] == "a" * 64


def test_dry_run_does_not_write_manifest_or_audit(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    output_manifest = tmp_path / "derived.jsonl"
    audit_report = tmp_path / "audit.json"
    _write_jsonl(manifest, [_manifest_row()])
    _write_jsonl(overrides, [_override_row()])
    _write_jsonl(ledger, [_ledger_row()])

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--overrides",
            str(overrides),
            "--source-ledger",
            str(ledger),
            "--output-manifest",
            str(output_manifest),
            "--audit-report",
            str(audit_report),
            "--dry-run",
            "--strict",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert not output_manifest.exists()
    assert not audit_report.exists()
    assert json.loads(completed.stdout)["summary"]["promoted_documents"] == 1


def test_repeated_runs_are_deterministic(tmp_path):
    module = _load_module()
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    first_manifest = tmp_path / "first_manifest.jsonl"
    first_audit = tmp_path / "first_audit.json"
    second_manifest = tmp_path / "second_manifest.jsonl"
    second_audit = tmp_path / "second_audit.json"
    _write_jsonl(manifest, [_manifest_row()])
    _write_jsonl(overrides, [_override_row()])
    _write_jsonl(ledger, [_ledger_row()])

    first = module.build_verified_manifest(
        manifest_path=manifest,
        overrides_path=overrides,
        source_ledger_path=ledger,
    )
    second = module.build_verified_manifest(
        manifest_path=manifest,
        overrides_path=overrides,
        source_ledger_path=ledger,
    )
    module.write_outputs(first, output_manifest=first_manifest, audit_report=first_audit)
    module.write_outputs(second, output_manifest=second_manifest, audit_report=second_audit)

    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    assert first_audit.read_bytes() == second_audit.read_bytes()


def test_duplicate_document_id_is_explicitly_audited(tmp_path):
    result = _run_builder(tmp_path, [_manifest_row(), _manifest_row()], [_override_row()], [_ledger_row()])

    assert result.audit["summary"]["rejection_reason_counts"] == {"duplicate_document_id": 2}
    assert result.audit["summary"]["hard_error_count"] == 2
    assert result.audit["admission_results"][0]["reason"] == "duplicate_document_id"


def test_audit_contains_no_body_chunk_path_env_or_secret_payload(tmp_path):
    result = _run_builder(tmp_path, [_manifest_row()], [_override_row()], [])

    audit_text = json.dumps(result.audit, sort_keys=True)
    forbidden = [
        "chunk text that must not appear",
        "raw/path",
        ".env",
        "SECRET",
        "API_KEY",
        "source_relpath",
        "body",
    ]
    assert all(token not in audit_text for token in forbidden)


def _run_builder(
    tmp_path: Path,
    manifest_rows: list[dict[str, object]],
    override_rows: list[dict[str, object]],
    ledger_rows: list[dict[str, object]],
):
    module = _load_module()
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    _write_jsonl(manifest, manifest_rows)
    _write_jsonl(overrides, override_rows)
    _write_jsonl(ledger, ledger_rows)
    return module.build_verified_manifest(
        manifest_path=manifest,
        overrides_path=overrides,
        source_ledger_path=ledger,
    )
