#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


OFFICIAL_RELEASE_COHORT = "official_release"
UNSUPPORTED_COHORT = "unsupported"
SUPPORTED_PDF_EXTENSIONS = frozenset({".pdf"})
UNSUPPORTED_IMAGE_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png", ".tif", ".tiff"})


@dataclass(frozen=True)
class ExtractedPDF:
    page_count: int
    pages: list[str]
    tables: list[tuple[int, list[list[str]]]]


class PDFExtractor(Protocol):
    def extract(self, path: Path) -> ExtractedPDF: ...


@dataclass(frozen=True)
class PreparedRelease:
    manifest_row: dict[str, Any]
    markdown: str | None


def prepare_official_releases(
    *,
    source_dir: Path,
    output_dir: Path,
    extractor: PDFExtractor | None = None,
) -> tuple[list[PreparedRelease], dict[str, Any]]:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    extractor = extractor or _PdfPlumberExtractor()
    source_files = _discover_source_files(source_dir)
    prepared: list[PreparedRelease] = []
    for source_path in source_files:
        prepared.append(_prepare_one(source_dir, output_dir, source_path, extractor))
    audit = _audit(prepared)
    return prepared, audit


def write_prepared_output(prepared: list[PreparedRelease], audit: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in prepared:
        row = item.manifest_row
        rows.append(row)
        if item.markdown is None:
            continue
        output_relpath = row.get("output_relpath")
        if not isinstance(output_relpath, str):
            continue
        path = output_dir / output_relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.markdown, encoding="utf-8", newline="\n")
    (metadata_dir / "official_release_manifest.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    (metadata_dir / "official_release_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _discover_source_files(source_dir: Path) -> list[Path]:
    candidates = []
    for root_name in ("BEA", "BLS"):
        root = source_dir / root_name
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(candidates, key=lambda path: str(path).lower())


def _prepare_one(source_dir: Path, output_dir: Path, source_path: Path, extractor: PDFExtractor) -> PreparedRelease:
    relpath = source_path.relative_to(source_dir).as_posix()
    profile = _profile_for_source(relpath, source_path.name)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if source_path.suffix.lower() in UNSUPPORTED_IMAGE_EXTENSIONS:
        return PreparedRelease(
            manifest_row=_unsupported_row(relpath, source_path, source_sha256, "ocr_required_image_method_page"),
            markdown=None,
        )
    if source_path.suffix.lower() not in SUPPORTED_PDF_EXTENSIONS:
        return PreparedRelease(
            manifest_row=_unsupported_row(relpath, source_path, source_sha256, "unsupported_extension"),
            markdown=None,
        )

    try:
        extracted = extractor.extract(source_path)
    except Exception as exc:
        return PreparedRelease(
            manifest_row=_unsupported_row(relpath, source_path, source_sha256, f"pdf_extract_failed:{type(exc).__name__}"),
            markdown=None,
        )

    full_text = "\n".join(extracted.pages)
    narrative_lines, table_like_lines = _split_narrative_and_tables(extracted.pages)
    text_char_count = len(full_text)
    extractable = text_char_count >= 300
    fields = _release_fields(profile, source_path.name, full_text)
    document_id = _document_id(fields)
    markdown = _markdown(
        title=fields["title"],
        fields=fields,
        narrative_lines=narrative_lines,
        table_like_lines=table_like_lines,
        extracted_tables=extracted.tables,
    )
    output_relpath = f"{OFFICIAL_RELEASE_COHORT}/{document_id}.md"
    cleaned_hash = _cleaned_content_sha256(markdown)
    row = {
        "document_id": document_id,
        "title": fields["title"],
        "cohort": OFFICIAL_RELEASE_COHORT,
        "output_relpath": output_relpath,
        "source_relpath": relpath,
        "original_filename": source_path.name,
        "source_file_sha256": source_sha256,
        "cleaned_content_sha256": cleaned_hash,
        "publisher": fields["publisher"],
        "source_kind": "official_release",
        "evidence_tier": "official_evidence",
        "is_official_source": True,
        "candidate_doc_type": "official_release",
        "runtime_doc_type": "official_release",
        "material_type": fields["material_type"],
        "release_date": fields["release_date"],
        "publication_date": fields["release_date"],
        "observation_period": fields["observation_period"],
        "vintage": "as_released",
        "factual_status": fields["factual_status"],
        "temporal_status": "historical_release",
        "not_current_observation": True,
        "rights_status": "official_public",
        "external_llm_context_allowed": True,
        "allowed_use": "external_context_candidate",
        "provenance_status": "verified",
        "provenance_basis": "user_curated_local_file",
        "source_reviewed_by_user": True,
        "extraction_status": "ready" if extractable else "review_required",
        "ingest_status": "eligible" if extractable else "hold",
        "page_count": extracted.page_count,
        "text_char_count": text_char_count,
        "extraction_method": "pdfplumber_text_and_tables",
        "content_layers": ["narrative", "table"],
        "table_quality": "review_required" if table_like_lines or extracted.tables else "not_detected",
        "review_reason": None if extractable else "low_text_extraction",
        "canonical_url": None,
        "source_domain": None,
    }
    return PreparedRelease(manifest_row=row, markdown=markdown)


def _unsupported_row(relpath: str, source_path: Path, source_sha256: str, reason: str) -> dict[str, Any]:
    profile = _profile_for_source(relpath, source_path.name)
    fields = _release_fields(profile, source_path.name, "")
    return {
        "document_id": _document_id(fields),
        "title": fields["title"],
        "cohort": UNSUPPORTED_COHORT,
        "output_relpath": None,
        "source_relpath": relpath,
        "original_filename": source_path.name,
        "source_file_sha256": source_sha256,
        "cleaned_content_sha256": None,
        "publisher": fields["publisher"],
        "source_kind": "official_release",
        "evidence_tier": "official_evidence",
        "is_official_source": True,
        "candidate_doc_type": "official_release",
        "runtime_doc_type": None,
        "material_type": fields["material_type"],
        "release_date": fields["release_date"],
        "publication_date": fields["release_date"],
        "observation_period": fields["observation_period"],
        "vintage": "as_released",
        "factual_status": fields["factual_status"],
        "temporal_status": "historical_release",
        "not_current_observation": True,
        "rights_status": "official_public",
        "external_llm_context_allowed": False,
        "allowed_use": "human_review_only",
        "provenance_status": "verified",
        "provenance_basis": "user_curated_local_file",
        "source_reviewed_by_user": True,
        "extraction_status": "unsupported",
        "ingest_status": "blocked",
        "page_count": None,
        "text_char_count": 0,
        "extraction_method": None,
        "content_layers": [],
        "table_quality": "unsupported",
        "review_reason": reason,
        "canonical_url": None,
        "source_domain": None,
    }


def _profile_for_source(relpath: str, filename: str) -> dict[str, str]:
    lowered = relpath.lower()
    name = filename.lower()
    if "bea/" in lowered and "gdp" in lowered:
        return {"publisher": "U.S. Bureau of Economic Analysis", "material_type": "gdp_third_estimate"}
    if "bea/" in lowered and "personal income" in lowered:
        return {"publisher": "U.S. Bureau of Economic Analysis", "material_type": "personal_income_and_outlays"}
    if "bea/" in lowered and "nipa" in lowered:
        return {"publisher": "U.S. Bureau of Economic Analysis", "material_type": "nipa_methodology_reference"}
    if "bls/" in lowered and "cpi" in name:
        return {"publisher": "U.S. Bureau of Labor Statistics", "material_type": "cpi_release"}
    if "bls/" in lowered and "ppi" in name:
        return {"publisher": "U.S. Bureau of Labor Statistics", "material_type": "ppi_release"}
    if "bls/" in lowered and "eci" in name:
        return {"publisher": "U.S. Bureau of Labor Statistics", "material_type": "eci_release"}
    if "bls/" in lowered and ("empsit" in name or "employment situation" in name):
        return {"publisher": "U.S. Bureau of Labor Statistics", "material_type": "employment_situation_release"}
    if "bls/" in lowered and "jolts" in name:
        return {"publisher": "U.S. Bureau of Labor Statistics", "material_type": "jolts_release"}
    return {"publisher": "unknown", "material_type": "official_release"}


def _release_fields(profile: dict[str, str], filename: str, text: str) -> dict[str, Any]:
    material_type = profile["material_type"]
    release_date = _release_date(text)
    observation_period = _observation_period(material_type, filename, text)
    title = _title(material_type, observation_period)
    return {
        "publisher": profile["publisher"],
        "material_type": material_type,
        "release_date": release_date,
        "observation_period": observation_period,
        "title": title,
        "factual_status": "methodology_reference" if material_type == "nipa_methodology_reference" else "historical_release",
    }


def _release_date(text: str) -> str | None:
    patterns = [
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday), ([A-Z][a-z]+ \d{1,2}, \d{4})",
        r"For release \d{1,2}:\d{2} [ap]\.m\. \(ET\) (?:Monday|Tuesday|Wednesday|Thursday|Friday), ([A-Z][a-z]+ \d{1,2}, \d{4})",
        r"(\d{1,2}:\d{2} [ap]\.m\. \(ET\) (?:Monday|Tuesday|Wednesday|Thursday|Friday), [A-Z][a-z]+ \d{1,2}, \d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:2000])
        if not match:
            continue
        value = match.group(1)
        value = value.split(") ")[-1] if ") " in value else value
        parsed = _parse_english_date(value)
        if parsed:
            return parsed
    return None


def _observation_period(material_type: str, filename: str, text: str) -> str | None:
    name = filename.lower()
    if material_type == "gdp_third_estimate":
        if match := re.search(r"gdp([1-4])q(\d{2})", name):
            return f"20{match.group(2)}-Q{match.group(1)}"
    if material_type == "personal_income_and_outlays":
        if "10-1125" in name:
            return "2025-10_to_2025-11"
        if match := re.search(r"pi(\d{2})(\d{2})", name):
            return f"20{match.group(2)}-{match.group(1)}"
    title_patterns = {
        "cpi_release": r"CONSUMER PRICE INDEX\s+[–-]\s+([A-Z]+ \d{4})",
        "ppi_release": r"PRODUCER PRICE INDEXES\s+[–-]\s+([A-Z]+ \d{4})",
        "eci_release": r"EMPLOYMENT COST INDEX\s+[–-]\s+([A-Z]+ \d{4})",
        "jolts_release": r"JOB OPENINGS AND LABOR TURNOVER\s+[–-]\s+([A-Z]+ \d{4})",
    }
    if material_type in title_patterns:
        if match := re.search(title_patterns[material_type], text[:4000], flags=re.IGNORECASE):
            return _month_year_to_period(match.group(1))
    if material_type == "employment_situation_release":
        if match := re.search(r"THE EMPLOYMENT SITUATION\s+[–-]\s+([A-Z]+ \d{4})", text[:6000], flags=re.IGNORECASE):
            return _month_year_to_period(match.group(1))
        if "2026 m05" in name:
            return "2026-05"
    if material_type == "nipa_methodology_reference":
        if match := re.search(r"(December \d{4})", text[:5000], flags=re.IGNORECASE):
            return _month_year_to_period(match.group(1))
    return None


def _title(material_type: str, observation_period: str | None) -> str:
    labels = {
        "gdp_third_estimate": "BEA GDP Third Estimate",
        "personal_income_and_outlays": "BEA Personal Income and Outlays",
        "nipa_methodology_reference": "BEA NIPA Concepts and Methods",
        "cpi_release": "BLS Consumer Price Index",
        "ppi_release": "BLS Producer Price Index",
        "eci_release": "BLS Employment Cost Index",
        "employment_situation_release": "BLS Employment Situation",
        "jolts_release": "BLS Job Openings and Labor Turnover",
    }
    label = labels.get(material_type, "Official Release")
    return f"{label} - {observation_period}" if observation_period else label


def _document_id(fields: dict[str, Any]) -> str:
    material_type = fields["material_type"]
    period = fields.get("observation_period") or "unknown"
    slug = period.lower().replace("-", "_").replace("_to_", "_to_")
    prefix = {
        "gdp_third_estimate": "bea_gdp_third_estimate",
        "personal_income_and_outlays": "bea_personal_income_and_outlays",
        "nipa_methodology_reference": "bea_nipa_methodology",
        "cpi_release": "bls_cpi",
        "ppi_release": "bls_ppi",
        "eci_release": "bls_eci",
        "employment_situation_release": "bls_employment_situation",
        "jolts_release": "bls_jolts",
    }.get(material_type, "official_release")
    return f"{prefix}_{slug}"


def _split_narrative_and_tables(pages: list[str]) -> tuple[list[str], list[str]]:
    narrative: list[str] = []
    tables: list[str] = []
    for page in pages:
        for raw_line in page.splitlines():
            line = _clean_line(raw_line)
            if not line:
                continue
            if _is_boilerplate(line):
                continue
            if _is_table_like(line):
                tables.append(line)
            else:
                narrative.append(line)
    return _dedupe_adjacent(narrative), _dedupe_adjacent(tables)


def _markdown(
    *,
    title: str,
    fields: dict[str, Any],
    narrative_lines: list[str],
    table_like_lines: list[str],
    extracted_tables: list[tuple[int, list[list[str]]]],
) -> str:
    header = [
        f"# {title}",
        "",
        "Issuer: " + str(fields["publisher"]),
        "Material Type: " + str(fields["material_type"]),
        "Release Date: " + str(fields["release_date"] or "unknown"),
        "Observation Period: " + str(fields["observation_period"] or "unknown"),
        "Vintage: as_released",
        "Factual Status: " + str(fields["factual_status"]),
        "Temporal Status: historical_release",
        "External LLM Context Allowed: true",
        "",
        "## Narrative Layer",
        "",
    ]
    narrative = _paragraphs(narrative_lines)
    table_section = [
        "",
        "## Table Layer",
        "",
        "Table Quality: review_required",
        "",
    ]
    if table_like_lines:
        table_section.extend(["### Table-like Extracted Lines", "", "```text"])
        table_section.extend(table_like_lines[:500])
        table_section.extend(["```", ""])
    for page_number, table in extracted_tables[:50]:
        table_section.extend([f"### Extracted Table Page {page_number}", "", "```tsv"])
        for row in table[:80]:
            table_section.append("\t".join(_clean_line(cell) for cell in row))
        table_section.extend(["```", ""])
    if not table_like_lines and not extracted_tables:
        table_section.append("No table-like text detected in deterministic extraction.")
    return "\n".join(header + narrative + table_section).strip() + "\n"


def _paragraphs(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in lines:
        if len(" ".join(buffer + [line])) > 900:
            if buffer:
                paragraphs.extend([" ".join(buffer), ""])
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        paragraphs.extend([" ".join(buffer), ""])
    return paragraphs


def _clean_line(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u2022", "-").split())


def _is_boilerplate(line: str) -> bool:
    lowered = line.lower()
    return lowered.startswith("technical:") or lowered.startswith("media contact:") or "pressoffice@" in lowered


def _is_table_like(line: str) -> bool:
    numeric_tokens = re.findall(r"[-+]?\$?\d[\d,]*(?:\.\d+)?%?", line)
    if len(numeric_tokens) >= 4:
        return True
    lowered = line.lower()
    return any(token in lowered for token in ("seasonally adjusted", "percent change", "billions of dollars", "table "))


def _dedupe_adjacent(lines: list[str]) -> list[str]:
    result: list[str] = []
    previous = None
    for line in lines:
        if line == previous:
            continue
        result.append(line)
        previous = line
    return result


def _month_year_to_period(value: str) -> str | None:
    parsed = _parse_english_date("1 " + value.title())
    if not parsed:
        return None
    return parsed[:7]


def _parse_english_date(value: str) -> str | None:
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _cleaned_content_sha256(markdown: str) -> str:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _audit(prepared: list[PreparedRelease]) -> dict[str, Any]:
    rows = [item.manifest_row for item in prepared]
    return {
        "source_documents": len(rows),
        "prepared_documents": sum(1 for row in rows if row.get("ingest_status") == "eligible"),
        "unsupported_documents": sum(1 for row in rows if row.get("ingest_status") == "blocked"),
        "cohort_counts": dict(sorted(Counter(row.get("cohort") for row in rows).items())),
        "material_type_counts": dict(sorted(Counter(row.get("material_type") for row in rows).items())),
        "extraction_status_counts": dict(sorted(Counter(row.get("extraction_status") for row in rows).items())),
        "table_quality_counts": dict(sorted(Counter(row.get("table_quality") for row in rows).items())),
    }


class _PdfPlumberExtractor:
    def extract(self, path: Path) -> ExtractedPDF:
        try:
            import pdfplumber  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("pdfplumber is required for PDF official release preparation") from exc
        pages: list[str] = []
        tables: list[tuple[int, list[list[str]]]] = []
        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                pages.append(page.extract_text() or "")
                for table in page.extract_tables() or []:
                    clean_table = [[_clean_line(cell) for cell in row] for row in table if row]
                    if clean_table:
                        tables.append((index, clean_table))
        return ExtractedPDF(page_count=len(pages), pages=pages, tables=tables)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare BEA/BLS official releases with narrative and table layers.")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.force and not args.dry_run:
        print(json.dumps({"status": "blocked", "reason": "output_dir_exists_use_force"}, sort_keys=True))
        return 2
    prepared, audit = prepare_official_releases(source_dir=args.source_dir, output_dir=args.output_dir)
    if args.dry_run:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    write_prepared_output(prepared, audit, args.output_dir)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
