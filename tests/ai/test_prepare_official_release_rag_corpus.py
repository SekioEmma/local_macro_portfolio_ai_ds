from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_official_release_rag_corpus.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_official_release_rag_corpus", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["prepare_official_release_rag_corpus"] = module
    spec.loader.exec_module(module)
    return module


class _FakeExtractor:
    def __init__(self, pages: list[str], tables=None) -> None:
        self._pages = pages
        self._tables = tables or []

    def extract(self, path: Path):
        module = _load_module()
        return module.ExtractedPDF(page_count=len(self._pages), pages=self._pages, tables=self._tables)


def test_bls_cpi_release_gets_narrative_and_table_layers(tmp_path):
    module = _load_module()
    source = tmp_path / "数据集"
    pdf = source / "BLS" / "cpi.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF fake")
    page = "\n".join(
        [
            "Transmission of material in this release is embargoed until USDL-26-0824",
            "8:30 a.m. (ET) Wednesday, June 10, 2026",
            "CONSUMER PRICE INDEX - MAY 2026",
            "The Consumer Price Index for All Urban Consumers increased 0.5 percent in May.",
            "The index for shelter rose in May and was the primary factor in the all items monthly increase. "
            "The food index also increased over the month, while the energy index moved higher after recent declines. "
            "This deterministic fixture is intentionally long enough to pass the text extraction threshold.",
            "Table A. Percent changes 0.5 2.1 3.4 4.0",
        ]
    )

    prepared, audit = module.prepare_official_releases(
        source_dir=source,
        output_dir=tmp_path / "out",
        extractor=_FakeExtractor([page], [(1, [["Series", "May"], ["CPI-U", "0.5"]])]),
    )

    assert audit["prepared_documents"] == 1
    row = prepared[0].manifest_row
    assert row["document_id"] == "bls_cpi_2026_05"
    assert row["runtime_doc_type"] == "official_release"
    assert row["material_type"] == "cpi_release"
    assert row["release_date"] == "2026-06-10"
    assert row["observation_period"] == "2026-05"
    assert row["factual_status"] == "historical_release"
    assert "## Narrative Layer" in prepared[0].markdown
    assert "## Table Layer" in prepared[0].markdown
    assert "```tsv" in prepared[0].markdown


def test_bea_personal_income_release_fields_from_filename_and_text(tmp_path):
    module = _load_module()
    source = tmp_path / "数据集"
    pdf = source / "BEA" / "Personal Income and Outlays" / "pi0126.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF fake")
    page = "\n".join(
        [
            "EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Friday, March 13, 2026 BEA 26-16",
            "Personal Income and Outlays, January 2026",
            "Personal income increased $113.8 billion in January.",
            "Seasonally adjusted annual rates 1 2 3 4",
        ]
    )

    prepared, _ = module.prepare_official_releases(
        source_dir=source,
        output_dir=tmp_path / "out",
        extractor=_FakeExtractor([page]),
    )

    row = prepared[0].manifest_row
    assert row["document_id"] == "bea_personal_income_and_outlays_2026_01"
    assert row["publisher"] == "U.S. Bureau of Economic Analysis"
    assert row["release_date"] == "2026-03-13"
    assert row["observation_period"] == "2026-01"
    assert row["table_quality"] == "review_required"


def test_image_method_pages_are_unsupported_and_not_written(tmp_path):
    module = _load_module()
    source = tmp_path / "数据集"
    image = source / "BLS" / "CPI方法页.jpeg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"jpeg")

    prepared, audit = module.prepare_official_releases(
        source_dir=source,
        output_dir=tmp_path / "out",
        extractor=_FakeExtractor([]),
    )

    assert audit["unsupported_documents"] == 1
    assert prepared[0].markdown is None
    assert prepared[0].manifest_row["ingest_status"] == "blocked"
    assert prepared[0].manifest_row["review_reason"] == "ocr_required_image_method_page"


def test_write_output_keeps_paths_manifest_only(tmp_path):
    module = _load_module()
    source = tmp_path / "数据集"
    pdf = source / "BLS" / "jolts.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF fake")
    page = "\n".join(
        [
            "For release 10:00 a.m. (ET) Tuesday, June 2, 2026 USDL-26-0783",
            "JOB OPENINGS AND LABOR TURNOVER - APRIL 2026",
            "The number of job openings increased to 7.6 million in April.",
        ]
    )
    output = tmp_path / "official_release_staging"
    prepared, audit = module.prepare_official_releases(
        source_dir=source,
        output_dir=output,
        extractor=_FakeExtractor([page]),
    )

    module.write_prepared_output(prepared, audit, output)

    manifest = output / "metadata" / "official_release_manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    markdown = (output / rows[0]["output_relpath"]).read_text(encoding="utf-8")
    assert rows[0]["source_relpath"] == "BLS/jolts.pdf"
    assert "source_relpath" not in markdown
    assert str(tmp_path) not in markdown
