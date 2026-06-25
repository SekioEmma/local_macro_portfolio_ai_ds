from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_fomc_source_ledger.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_fomc_source_ledger", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["prepare_fomc_source_ledger"] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _manifest_row(
    document_id: str,
    *,
    material_type: str = "statement",
    source_kind: str = "central_bank_policy",
    runtime_doc_type: str | None = "policy_doc",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "source_kind": source_kind,
        "runtime_doc_type": runtime_doc_type,
        "fomc_material_type": material_type,
        "source_relpath": f"FOMC/{document_id}.pdf",
        "source_file_sha256": "f" * 64,
        "release_date": "2026-06-17",
        "canonical_url": "https://example.com/must-not-copy",
        "body": "chunk text must not appear",
    }


def test_template_contains_only_fomc_policy_candidates_and_pending_fields(tmp_path):
    module = _load_module()
    manifest = tmp_path / "rag_manifest.jsonl"
    _write_jsonl(
        manifest,
        [
            _manifest_row("fomc_statement_2026_06_17", material_type="statement"),
            _manifest_row("fomc_minutes_2026_05_06", material_type="minutes"),
            _manifest_row("bls_cpi_2026_05", material_type="official_release", source_kind="official_release"),
            _manifest_row("imf_weo_2026_04", material_type="official_outlook", runtime_doc_type="research_report"),
            _manifest_row("memo_private", material_type="memo", source_kind="institutional_research"),
        ],
    )

    rows = module.build_template_rows(manifest)

    assert [row["document_id"] for row in rows] == [
        "fomc_minutes_2026_05_06",
        "fomc_statement_2026_06_17",
    ]
    assert {row["verification_status"] for row in rows} == {"pending_user_verification"}
    assert {row["canonical_url"] for row in rows} == {None}
    assert {row["source_domain"] for row in rows} == {None}
    assert {row["verified_by"] for row in rows} == {None}
    assert {row["verification_basis"] for row in rows} == {None}


def test_template_writes_deterministic_jsonl_without_manifest_body(tmp_path):
    module = _load_module()
    manifest = tmp_path / "rag_manifest.jsonl"
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _write_jsonl(
        manifest,
        [
            _manifest_row("fomc_statement_2026_06_17", material_type="statement"),
            _manifest_row("fomc_sep_2026_06_17", material_type="sep"),
        ],
    )

    rows = module.build_template_rows(manifest)
    module.write_template(rows, first)
    module.write_template(rows, second)

    assert first.read_bytes() == second.read_bytes()
    payload = first.read_text(encoding="utf-8")
    assert "chunk text must not appear" not in payload
    assert "https://example.com/must-not-copy" not in payload
    assert "source_relpath" in payload


def test_dry_run_prints_counts_and_writes_no_file(tmp_path):
    manifest = tmp_path / "rag_manifest.jsonl"
    output = tmp_path / "fomc_source_ledger_template.jsonl"
    _write_jsonl(manifest, [_manifest_row("fomc_statement_2026_06_17")])

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--output-ledger",
            str(output),
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert not output.exists()
    payload = json.loads(completed.stdout)
    assert payload["candidate_documents"] == 1
    assert payload["material_type_counts"] == {"statement": 1}


def test_existing_template_is_not_overwritten_without_force(tmp_path):
    module = _load_module()
    manifest = tmp_path / "rag_manifest.jsonl"
    output = tmp_path / "fomc_source_ledger_template.jsonl"
    _write_jsonl(manifest, [_manifest_row("fomc_statement_2026_06_17")])
    output.write_text("existing\n", encoding="utf-8")

    rows = module.build_template_rows(manifest)

    try:
        module.write_template(rows, output)
    except FileExistsError as exc:
        assert "refusing_to_overwrite_existing_template" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")
    assert output.read_text(encoding="utf-8") == "existing\n"
