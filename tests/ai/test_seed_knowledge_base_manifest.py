from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_seed_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "seed_knowledge_base.py"
    spec = importlib.util.spec_from_file_location("seed_knowledge_base", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_knowledge_base"] = module
    spec.loader.exec_module(module)
    return module


def _row(
    *,
    document_id: str,
    output_relpath: str,
    cohort: str = "policy_doc",
    ingest_status: str = "eligible",
    runtime_doc_type: str = "policy_doc",
    external_llm_context_allowed: bool = True,
    allowed_use: str = "external_context_candidate",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "output_relpath": output_relpath,
        "cohort": cohort,
        "ingest_status": ingest_status,
        "extraction_status": "ready",
        "provenance_status": "verified",
        "runtime_doc_type": runtime_doc_type,
        "external_llm_context_allowed": external_llm_context_allowed,
        "allowed_use": allowed_use,
    }


def _write_manifest(staging_root: Path, rows: list[dict[str, object]]) -> Path:
    metadata = staging_root / "metadata"
    metadata.mkdir(parents=True)
    manifest = metadata / "rag_manifest.jsonl"
    manifest.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
    return manifest


def test_manifest_documents_keep_only_external_seed_candidates(tmp_path):
    seed_module = _load_seed_module()
    staging = tmp_path / "rag_staging"
    (staging / "policy_doc").mkdir(parents=True)
    (staging / "research_report").mkdir()
    (staging / "local_only").mkdir()
    (staging / "pending_governance").mkdir()
    (staging / "review_required").mkdir()

    for relpath in [
        "policy_doc/fomc_statement_2026_06_17.md",
        "research_report/imf_weo_2026_04.md",
        "local_only/private_memo.md",
        "pending_governance/bls_cpi.md",
        "review_required/fomc_duplicate.md",
    ]:
        (staging / relpath).write_text("# Title\nBody", encoding="utf-8")

    manifest = _write_manifest(
        staging,
        [
            _row(document_id="fomc_statement_2026_06_17", output_relpath="policy_doc/fomc_statement_2026_06_17.md"),
            _row(
                document_id="imf_weo_2026_04",
                output_relpath="research_report/imf_weo_2026_04.md",
                cohort="research_report",
                runtime_doc_type="research_report",
            ),
            _row(
                document_id="private_memo",
                output_relpath="local_only/private_memo.md",
                cohort="local_only",
                runtime_doc_type="research_report",
                ingest_status="local_only",
                external_llm_context_allowed=False,
                allowed_use="local_search_only",
            ),
            _row(
                document_id="bls_cpi",
                output_relpath="pending_governance/bls_cpi.md",
                cohort="pending_governance",
                ingest_status="hold",
                runtime_doc_type=None,
            ),
            _row(
                document_id="fomc_duplicate",
                output_relpath="review_required/fomc_duplicate.md",
                cohort="review_required",
            ),
        ],
    )

    docs = seed_module._manifest_documents(manifest)

    assert [doc.doc_id for doc in docs] == [
        "fomc_statement_2026_06_17",
        "imf_weo_2026_04",
    ]
    assert {doc.doc_type for doc in docs} == {"policy_doc", "research_report"}
    assert all(doc.external_llm_context_allowed is True for doc in docs)


def test_seed_manifest_dry_run_uses_stable_manifest_document_id(tmp_path, capsys):
    seed_module = _load_seed_module()
    staging = tmp_path / "rag_staging"
    (staging / "policy_doc").mkdir(parents=True)
    (staging / "policy_doc" / "fomc_statement_2026_06_17.md").write_text(
        "# FOMC Statement - 2026-06-17\nThe Committee decided to maintain the target range.",
        encoding="utf-8",
    )
    manifest = _write_manifest(
        staging,
        [
            _row(
                document_id="fomc_statement_2026_06_17",
                output_relpath="policy_doc/fomc_statement_2026_06_17.md",
            )
        ],
    )

    result = seed_module.seed(
        scan_dir=tmp_path / "unused",
        vector_dir=tmp_path / "vector_store",
        doc_type="research_report",
        write=False,
        manifest_path=manifest,
    )

    captured = capsys.readouterr()
    assert result["files"] == 1
    assert result["written"] == 0
    assert "doc_id=fomc_statement_2026_06_17" in captured.out
    assert "doc_type=policy_doc" in captured.out


def test_seed_scan_dir_falls_back_to_bm25_only_when_vector_unavailable(
    tmp_path, capsys, monkeypatch
):
    seed_module = _load_seed_module()
    scan_dir = tmp_path / "memo"
    scan_dir.mkdir()
    (scan_dir / "research_report_x.md").write_text(
        "# Research Report X\nGlobal outlook commentary text.",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed_module, "_CHUNK_TEXT_DB", tmp_path / "vector_store" / "chunks.sqlite")

    import sys
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    result = seed_module.seed(
        scan_dir=scan_dir,
        vector_dir=tmp_path / "vector_store",
        doc_type="research_report",
        write=True,
    )

    captured = capsys.readouterr()
    assert result["files"] == 1
    assert result["chunks"] >= 1
    assert result["written"] == result["chunks"]
    assert "write-bm25-only" in captured.out
    from llm.chunk_text_store import ChunkTextStore
    store = ChunkTextStore(tmp_path / "vector_store" / "chunks.sqlite")
    assert store.count() == result["written"]
    assert not (tmp_path / "vector_store" / "chroma").exists()


def test_seed_scan_dir_writes_chroma_to_chroma_subdirectory(
    tmp_path, monkeypatch
):
    seed_module = _load_seed_module()
    scan_dir = tmp_path / "memo"
    scan_dir.mkdir()
    (scan_dir / "research_report_x.md").write_text(
        "# Research Report X\nGlobal outlook commentary text.",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed_module, "_CHUNK_TEXT_DB", tmp_path / "vector_store" / "chunks.sqlite")

    captured: dict[str, object] = {}

    class _FakeVectorStore:
        def __init__(self, persist_dir):
            captured["persist_dir"] = persist_dir

        def upsert(self, *args, **kwargs):
            captured.setdefault("upserts", 0)
            captured["upserts"] = captured["upserts"] + 1  # type: ignore[operator]

    class _FakeEmbeddingService:
        def __init__(self, *args, **kwargs):
            pass

        def load(self):
            return None

        def encode(self, texts):
            return [[0.0] * 4 for _ in texts]

    import sys
    fake_module = type(sys)("llm.vector_store")
    fake_module.VectorStore = _FakeVectorStore  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm.vector_store", fake_module)
    fake_emb_module = type(sys)("llm.embedding_service")
    fake_emb_module.EmbeddingService = _FakeEmbeddingService  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm.embedding_service", fake_emb_module)

    seed_module.seed(
        scan_dir=scan_dir,
        vector_dir=tmp_path / "vector_store",
        doc_type="research_report",
        write=True,
    )

    from pathlib import Path
    assert captured["persist_dir"] == Path(tmp_path / "vector_store" / "chroma")
    assert captured.get("upserts", 0) >= 1
