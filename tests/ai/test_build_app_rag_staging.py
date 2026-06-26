from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_app_rag_staging.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_app_rag_staging", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_app_rag_staging"] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_doc(root: Path, relpath: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {Path(relpath).stem}\n\nBody", encoding="utf-8")


def test_merge_replaces_pending_official_release_and_authorizes_institutional_view(tmp_path):
    module = _load_module()
    base_root = tmp_path / "base"
    official_root = tmp_path / "official"
    output_root = tmp_path / "merged"
    _write_doc(base_root, "policy_doc/fomc.md")
    _write_doc(base_root, "pending_governance/bls_cpi.md")
    _write_doc(base_root, "local_only/memo.md")
    _write_doc(official_root, "official_release/bls_cpi.md")

    base_rows = [
        {
            "document_id": "fomc_statement_2026_06_17",
            "cohort": "policy_doc",
            "output_relpath": "policy_doc/fomc.md",
            "runtime_doc_type": "policy_doc",
            "source_kind": "central_bank_policy",
        },
        {
            "document_id": "bls_cpi_2026_05",
            "cohort": "pending_governance",
            "output_relpath": "pending_governance/bls_cpi.md",
            "runtime_doc_type": None,
            "source_kind": "official_release",
        },
        {
            "document_id": "research_report_macro_view",
            "cohort": "local_only",
            "output_relpath": "local_only/memo.md",
            "runtime_doc_type": "research_report",
            "candidate_doc_type": "research_report",
            "source_kind": "institutional_research",
            "external_llm_context_allowed": False,
            "allowed_use": "local_search_only",
            "ingest_status": "local_only",
            "rights_status": "private_local_only",
        },
    ]
    official_rows = [
        {
            "document_id": "bls_cpi_2026_05",
            "cohort": "official_release",
            "output_relpath": "official_release/bls_cpi.md",
            "runtime_doc_type": "official_release",
            "source_kind": "official_release",
        }
    ]
    base_manifest = base_root / "metadata" / "derived_manifest.jsonl"
    official_manifest = official_root / "metadata" / "official_release_manifest.jsonl"
    _write_jsonl(base_manifest, base_rows)
    _write_jsonl(official_manifest, official_rows)

    result = module.build_app_rag_staging(
        base_root=base_root,
        base_manifest=base_manifest,
        official_root=official_root,
        official_manifest=official_manifest,
        authorize_institutional_external_context=True,
    )
    module.write_merge_result(result, output_root)

    rows = [item.row for item in result.rows]
    by_id = {row["document_id"]: row for row in rows}
    memo = by_id["research_report_macro_view"]

    assert result.audit["removed_base_official_release_rows"] == 1
    assert by_id["bls_cpi_2026_05"]["cohort"] == "official_release"
    assert memo["cohort"] == "research_report"
    assert memo["output_relpath"] == "research_report/memo.md"
    assert memo["external_llm_context_allowed"] is True
    assert memo["allowed_use"] == "external_context_candidate"
    assert memo["evidence_tier"] == "institutional_view"
    assert memo["is_official_source"] is False
    assert (output_root / "research_report" / "memo.md").exists()
    assert (output_root / "official_release" / "bls_cpi.md").exists()


def test_merge_without_authorization_keeps_institutional_local_only(tmp_path):
    module = _load_module()
    base_root = tmp_path / "base"
    official_root = tmp_path / "official"
    _write_doc(base_root, "local_only/memo.md")
    base_manifest = base_root / "metadata" / "derived_manifest.jsonl"
    official_manifest = official_root / "metadata" / "official_release_manifest.jsonl"
    _write_jsonl(
        base_manifest,
        [
            {
                "document_id": "research_report_macro_view",
                "cohort": "local_only",
                "output_relpath": "local_only/memo.md",
                "runtime_doc_type": "research_report",
                "source_kind": "institutional_research",
                "external_llm_context_allowed": False,
                "allowed_use": "local_search_only",
                "ingest_status": "local_only",
            }
        ],
    )
    _write_jsonl(official_manifest, [])

    result = module.build_app_rag_staging(
        base_root=base_root,
        base_manifest=base_manifest,
        official_root=official_root,
        official_manifest=official_manifest,
        authorize_institutional_external_context=False,
    )

    row = result.rows[0].row
    assert row["cohort"] == "local_only"
    assert row["external_llm_context_allowed"] is False
    assert row["evidence_tier"] == "institutional_view"
    assert row["is_official_source"] is False
