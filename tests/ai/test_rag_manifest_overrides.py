from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "apply_rag_manifest_overrides.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("apply_rag_manifest_overrides", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["apply_rag_manifest_overrides"] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> bytes:
    payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path.read_bytes()


def _manifest_row(document_id: str = "fomc_statement_2026_06_17") -> dict[str, object]:
    return {
        "document_id": document_id,
        "canonical_url": None,
        "source_domain": "www.federalreserve.gov",
        "runtime_doc_type": "policy_doc",
        "external_llm_context_allowed": True,
        "ingest_status": "eligible",
        "local_only": False,
        "body": "text that must not appear in audit",
        "source_relpath": "raw/path/that/must/not/appear.pdf",
    }


def _override(
    document_id: str = "fomc_statement_2026_06_17",
    canonical_url: str = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
    source_domain: str = "www.federalreserve.gov",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "canonical_url": canonical_url,
        "source_domain": source_domain,
    }


def test_valid_override_generates_derived_manifest_and_only_allowed_fields_change(tmp_path):
    module = _load_module()
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    original = _manifest_row()
    original_bytes = _write_jsonl(manifest, [original])
    _write_jsonl(overrides, [_override()])

    result = module.apply_overrides(manifest_path=manifest, overrides_path=overrides)

    assert manifest.read_bytes() == original_bytes
    assert result.audit["summary"]["accepted_overrides"] == 1
    derived = result.derived_rows[0]
    changed_keys = {key for key in set(original) | set(derived) if original.get(key) != derived.get(key)}
    assert changed_keys == {"canonical_url", "metadata_override_applied"}
    assert derived["source_domain"] == original["source_domain"]


def test_original_manifest_file_bytes_are_not_modified_when_writing_outputs(tmp_path):
    module = _load_module()
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    output_manifest = tmp_path / "derived.jsonl"
    audit_report = tmp_path / "audit.json"
    original_bytes = _write_jsonl(manifest, [_manifest_row()])
    _write_jsonl(overrides, [_override()])

    result = module.apply_overrides(manifest_path=manifest, overrides_path=overrides)
    module.write_outputs(result, output_manifest=output_manifest, audit_report=audit_report)

    assert manifest.read_bytes() == original_bytes
    assert output_manifest.exists()
    assert audit_report.exists()


def test_non_https_url_is_rejected(tmp_path):
    result = _run_apply(
        tmp_path,
        [_manifest_row()],
        [_override(canonical_url="http://www.federalreserve.gov/doc")],
    )
    assert result.audit["summary"]["rejection_reason_counts"] == {"non_https_url": 1}


def test_url_host_source_domain_mismatch_is_rejected(tmp_path):
    result = _run_apply(
        tmp_path,
        [_manifest_row()],
        [_override(source_domain="federalreserve.gov")],
    )
    assert result.audit["summary"]["rejection_reason_counts"] == {"source_domain_host_mismatch": 1}


def test_source_domain_conflict_with_manifest_is_rejected(tmp_path):
    row = _manifest_row()
    row["source_domain"] = "www.federalreserve.gov"
    result = _run_apply(
        tmp_path,
        [row],
        [_override(
            canonical_url="https://www.sec.gov/doc",
            source_domain="www.sec.gov",
        )],
    )
    assert result.audit["summary"]["rejection_reason_counts"] == {"source_domain_conflicts_with_manifest": 1}


def test_duplicate_override_document_id_is_rejected(tmp_path):
    result = _run_apply(tmp_path, [_manifest_row()], [_override(), _override()])
    assert result.audit["summary"]["rejection_reason_counts"] == {"duplicate_override_document_id": 2}


def test_duplicate_canonical_url_for_different_documents_is_rejected(tmp_path):
    row2 = _manifest_row("fomc_statement_2026_04_29")
    result = _run_apply(
        tmp_path,
        [_manifest_row(), row2],
        [
            _override("fomc_statement_2026_06_17"),
            _override("fomc_statement_2026_04_29"),
        ],
    )
    assert result.audit["summary"]["rejection_reason_counts"] == {"duplicate_canonical_url": 2}


def test_unknown_document_id_is_rejected(tmp_path):
    result = _run_apply(tmp_path, [_manifest_row()], [_override("missing_doc")])
    assert result.audit["summary"]["rejection_reason_counts"] == {"unknown_document_id": 1}


def test_manifest_duplicate_document_id_is_explicitly_audited(tmp_path):
    result = _run_apply(tmp_path, [_manifest_row(), _manifest_row()], [])
    assert result.audit["summary"]["rejection_reason_counts"] == {"duplicate_manifest_document_id": 2}
    assert result.audit["manifest_results"][0]["reason"] == "duplicate_manifest_document_id"


def test_existing_canonical_url_cannot_be_replaced(tmp_path):
    row = _manifest_row()
    row["canonical_url"] = "https://www.federalreserve.gov/existing"
    result = _run_apply(tmp_path, [row], [_override()])
    assert result.audit["summary"]["rejection_reason_counts"] == {"canonical_url_already_present": 1}
    assert result.derived_rows[0]["canonical_url"] == "https://www.federalreserve.gov/existing"


def test_local_only_and_external_llm_false_are_not_changed(tmp_path):
    row = _manifest_row("private_memo")
    row["local_only"] = True
    row["external_llm_context_allowed"] = False
    result = _run_apply(
        tmp_path,
        [row],
        [_override("private_memo")],
    )
    derived = result.derived_rows[0]
    assert derived["local_only"] is True
    assert derived["external_llm_context_allowed"] is False
    assert derived["metadata_override_applied"] is True


def test_unknown_override_field_is_rejected(tmp_path):
    result = _run_apply(
        tmp_path,
        [_manifest_row()],
        [{**_override(), "doc_type": "research_report"}],
    )
    assert result.audit["summary"]["rejection_reason_counts"] == {"unknown_override_field": 1}


def test_dry_run_does_not_generate_files(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    output_manifest = tmp_path / "derived.jsonl"
    audit_report = tmp_path / "audit.json"
    _write_jsonl(manifest, [_manifest_row()])
    _write_jsonl(overrides, [_override()])

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--overrides",
            str(overrides),
            "--output-manifest",
            str(output_manifest),
            "--audit-report",
            str(audit_report),
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert not output_manifest.exists()
    assert not audit_report.exists()
    assert json.loads(completed.stdout)["summary"]["accepted_overrides"] == 1


def test_strict_invalid_override_returns_nonzero_and_writes_no_files(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    output_manifest = tmp_path / "derived.jsonl"
    audit_report = tmp_path / "audit.json"
    _write_jsonl(manifest, [_manifest_row()])
    _write_jsonl(overrides, [_override(canonical_url="http://www.federalreserve.gov/doc")])

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--overrides",
            str(overrides),
            "--output-manifest",
            str(output_manifest),
            "--audit-report",
            str(audit_report),
            "--strict",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert not output_manifest.exists()
    assert not audit_report.exists()


def test_audit_output_contains_no_text_chunk_paths_env_or_secrets(tmp_path):
    result = _run_apply(tmp_path, [_manifest_row()], [_override(canonical_url="http://www.federalreserve.gov/doc")])
    audit_text = json.dumps(result.audit, sort_keys=True)
    forbidden = [
        "text that must not appear",
        "chunk",
        "raw/path",
        ".env",
        "SECRET",
        "API_KEY",
        "source_relpath",
    ]
    assert all(token not in audit_text for token in forbidden)


def _run_apply(
    tmp_path: Path,
    manifest_rows: list[dict[str, object]],
    override_rows: list[dict[str, object]],
):
    module = _load_module()
    manifest = tmp_path / "manifest.jsonl"
    overrides = tmp_path / "overrides.jsonl"
    _write_jsonl(manifest, manifest_rows)
    _write_jsonl(overrides, override_rows)
    return module.apply_overrides(manifest_path=manifest, overrides_path=overrides)

