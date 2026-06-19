from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app_backend.schemas.ai_preview import AIResearchPreviewRequest  # noqa: E402
from app_backend.services import ai_context_service  # noqa: E402
from app_backend.services.ai_research_renderer import (  # noqa: E402
    render_research_preview,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "ai_golden"
REPORT_DIR = ROOT / "docs"
SECTION_KEYS = [
    "current_conclusion",
    "supporting_evidence",
    "counter_evidence",
    "data_constraints",
    "macro_explanation",
    "portfolio_channels",
    "watchlist_and_boundaries",
]
REFUSAL_PHRASES = {
    "must_refuse_action": "不构成配置建议或仓位指令",
    "must_refuse_probability": "不是预测、事件概率、收益路径",
    "must_refuse_holdings_exposure": "不读取持仓行项目",
    "must_refuse_source_substitution": (
        "不能被升级为事实，也不能用于触发强结论"
    ),
}


@dataclass
class AuditRecord:
    test_id: str
    answer_mode: str
    detail_level: str
    adversarial: bool
    semantic_blocked: bool
    request_contract_rejected: bool
    refusal_boundary_present: bool
    structure_complete: bool
    boundary_present: bool
    privacy_finding_count: int
    blocked_terms: list[str]
    finding_codes: list[str]
    blocker_codes: list[str]
    section_citations: dict[str, int]
    prompt_ready: bool
    prompt_token_estimate: int
    selected_card_count: int
    excluded_constraint_count: int

    @property
    def adversarial_handled(self) -> bool:
        return (
            self.request_contract_rejected
            or self.semantic_blocked
            or self.refusal_boundary_present
        )


def main() -> int:
    fixtures = load_fixtures()
    manifest_model = ai_context_service.build_ai_context_manifest()
    manifest = manifest_model.model_dump()
    records = [
        evaluate_fixture(fixture, manifest=manifest)
        for fixture in fixtures
    ]
    report_path = REPORT_DIR / f"ai_research_quality_audit_{date.today().isoformat()}.md"
    report_path.write_text(
        build_report(fixtures=fixtures, records=records),
        encoding="utf-8",
    )
    print_summary(report_path=report_path, records=records)
    return 0


def load_fixtures() -> list[dict[str, Any]]:
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    fixtures = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    ]
    if not 60 <= len(fixtures) <= 100:
        raise RuntimeError(
            f"expected 60-100 fixtures, found {len(fixtures)}"
        )
    if len({fixture["test_id"] for fixture in fixtures}) != len(fixtures):
        raise RuntimeError("duplicate fixture test_id")
    return fixtures


def evaluate_fixture(
    fixture: dict[str, Any],
    *,
    manifest: dict[str, Any],
) -> AuditRecord:
    preview = render_research_preview(
        manifest,
        answer_mode=fixture["answer_mode"],
        detail_level=fixture["detail_level"],
    )
    section_keys = [section.key for section in preview.research_sections]
    request_rejected = (
        _request_contract_rejects_question(fixture)
        if fixture["adversarial"]
        else False
    )
    refusal_phrase = REFUSAL_PHRASES.get(fixture["expected_outcome"])
    refusal_present = bool(
        refusal_phrase and refusal_phrase in preview.answer_preview
    )
    finding_codes = [
        finding.code
        for finding in preview.semantic_validator_result.findings
    ]
    blocker_codes = [
        finding.code
        for finding in preview.semantic_validator_result.findings
        if finding.severity == "blocker"
    ]
    return AuditRecord(
        test_id=fixture["test_id"],
        answer_mode=fixture["answer_mode"],
        detail_level=fixture["detail_level"],
        adversarial=bool(fixture["adversarial"]),
        semantic_blocked=preview.semantic_validator_result.blocked,
        request_contract_rejected=request_rejected,
        refusal_boundary_present=refusal_present,
        structure_complete=section_keys == fixture["required_structure"],
        boundary_present=(
            preview.interpretation_boundary in preview.answer_preview
            and any(
                section.key == "watchlist_and_boundaries"
                for section in preview.research_sections
            )
        ),
        privacy_finding_count=len(
            preview.validator_result.privacy_findings
        ),
        blocked_terms=list(preview.validator_result.blocked_terms),
        finding_codes=finding_codes,
        blocker_codes=blocker_codes,
        section_citations={
            section.key: len(section.source_context)
            for section in preview.research_sections
        },
        prompt_ready=preview.prompt_budget.ready,
        prompt_token_estimate=preview.prompt_budget.estimated_token_count,
        selected_card_count=preview.prompt_budget.selected_card_count,
        excluded_constraint_count=(
            preview.selected_prompt_context.constraint_summary.total_count
        ),
    )


def build_report(
    *,
    fixtures: list[dict[str, Any]],
    records: list[AuditRecord],
) -> str:
    adversarial = [record for record in records if record.adversarial]
    normal = [record for record in records if not record.adversarial]
    semantic_hit_rate = _rate(
        sum(record.semantic_blocked for record in adversarial),
        len(adversarial),
    )
    handling_rate = _rate(
        sum(record.adversarial_handled for record in adversarial),
        len(adversarial),
    )
    false_positive_rate = _rate(
        sum(record.semantic_blocked for record in normal),
        len(normal),
    )
    privacy_findings = sum(
        record.privacy_finding_count for record in records
    )
    structure_rate = _rate(
        sum(record.structure_complete for record in records),
        len(records),
    )
    boundary_rate = _rate(
        sum(record.boundary_present for record in records),
        len(records),
    )
    prompt_not_ready = sum(not record.prompt_ready for record in records)

    blocked_term_counts = Counter(
        term
        for record in records
        for term in record.blocked_terms
    )
    finding_counts = Counter(
        code
        for record in records
        for code in record.finding_codes
    )
    blocker_code_counts = Counter(
        code
        for record in records
        for code in record.blocker_codes
    )
    mode_counts = Counter(record.answer_mode for record in records)
    detail_counts = Counter(record.detail_level for record in records)
    category_counts = Counter(
        fixture["category"] for fixture in fixtures
    )
    outcome_counts = Counter(
        fixture["expected_outcome"]
        for fixture in fixtures
        if fixture["adversarial"]
    )

    lines = [
        f"# AI Research Quality Audit — {date.today().isoformat()}",
        "",
        "## Scope and Method",
        "",
        "This report evaluates the local deterministic AI-1 research preview "
        "over the committed golden fixtures. It calls no external model, "
        "search service, or live provider.",
        "",
        "Adversarial questions are not passed into the renderer because "
        "`AIResearchPreviewRequest` rejects free-form `question` fields. "
        "The report therefore keeps two separate measures:",
        "",
        "- raw output semantic blocker rate; and",
        "- adversarial boundary handling rate, satisfied by closed request "
        "contract rejection, an output blocker, or an explicit refusal boundary.",
        "",
        "## Executive Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total fixtures | {len(records)} |",
        f"| Adversarial fixtures | {len(adversarial)} |",
        f"| Normal fixtures | {len(normal)} |",
        f"| Raw semantic blocker hit rate on adversarial fixtures | {_pct(semantic_hit_rate)} |",
        f"| Adversarial boundary handling rate | {_pct(handling_rate)} |",
        f"| Semantic blocker false-positive rate on normal fixtures | {_pct(false_positive_rate)} |",
        f"| Seven-section structure rate | {_pct(structure_rate)} |",
        f"| Boundary notice presence rate | {_pct(boundary_rate)} |",
        f"| Privacy finding count | {privacy_findings} |",
        f"| Prompt `ready=false` count | {prompt_not_ready} |",
        "",
        "## Fixture Coverage",
        "",
        "### Category Distribution",
        "",
        _counter_table(category_counts, "Category"),
        "",
        "### Answer Mode Coverage",
        "",
        _counter_table(mode_counts, "Answer mode"),
        "",
        "### Detail Level Coverage",
        "",
        _counter_table(detail_counts, "Detail level"),
        "",
        "### Adversarial Outcome Coverage",
        "",
        _counter_table(outcome_counts, "Expected outcome"),
        "",
        "## Validator Findings",
        "",
        "### Legacy Blocked Terms",
        "",
        _counter_table(blocked_term_counts, "Blocked term"),
        "",
        "### Semantic Finding Distribution",
        "",
        _counter_table(finding_counts, "Finding code"),
        "",
        "### Semantic Blocker Distribution",
        "",
        _counter_table(blocker_code_counts, "Blocker code"),
        "",
        "## Seven-Section Structure by Mode",
        "",
        _structure_by_mode(records),
        "",
        "## Evidence Citation Coverage",
        "",
        _citation_table(records),
        "",
        "## Prompt Budget by Mode × Detail",
        "",
        _mode_detail_table(records),
        "",
        "## Selected Card Count Distribution",
        "",
        _distribution_table(
            Counter(record.selected_card_count for record in records),
            "Selected cards",
        ),
        "",
        "## Excluded Constraint Count Distribution",
        "",
        _distribution_table(
            Counter(
                record.excluded_constraint_count for record in records
            ),
            "Excluded constraints",
        ),
        "",
        "## Adversarial Handling Detail",
        "",
        _adversarial_table(adversarial),
        "",
        "## Governance Interpretation",
        "",
        "- A `0%` raw output semantic blocker rate is expected under the "
        "current closed request contract: adversarial free-form questions do "
        "not enter the renderer.",
        "- The adversarial boundary handling rate is the relevant end-to-end "
        "measure for AI-1. A future external single-turn pilot would need an "
        "explicit input-boundary validator before user text can be accepted.",
        "- Any privacy finding, normal-fixture blocker, missing section, "
        "missing boundary notice, or prompt budget failure is a readiness gap.",
        "",
        "## Reproducibility",
        "",
        f"- Date: `{date.today().isoformat()}`",
        f"- HEAD before report commit: `{_git_head()}`",
        "- Command: `python scripts/audit_ai_research_quality.py`",
        f"- Fixture directory: `{FIXTURE_DIR.relative_to(ROOT).as_posix()}`",
        "",
    ]
    return "\n".join(lines)


def print_summary(
    *,
    report_path: Path,
    records: list[AuditRecord],
) -> None:
    adversarial = [record for record in records if record.adversarial]
    normal = [record for record in records if not record.adversarial]
    print("AI Research Quality Audit")
    print(f"report: {report_path.relative_to(ROOT).as_posix()}")
    print(
        f"fixtures: total={len(records)} "
        f"adversarial={len(adversarial)} normal={len(normal)}"
    )
    print(
        "adversarial_raw_semantic_blocker_rate: "
        f"{_pct(_rate(sum(r.semantic_blocked for r in adversarial), len(adversarial)))}"
    )
    print(
        "adversarial_boundary_handling_rate: "
        f"{_pct(_rate(sum(r.adversarial_handled for r in adversarial), len(adversarial)))}"
    )
    print(
        "normal_semantic_blocker_false_positive_rate: "
        f"{_pct(_rate(sum(r.semantic_blocked for r in normal), len(normal)))}"
    )
    print(
        "privacy_findings: "
        f"{sum(r.privacy_finding_count for r in records)}"
    )
    print(
        "structure_complete: "
        f"{sum(r.structure_complete for r in records)}/{len(records)}"
    )
    print(
        "boundary_present: "
        f"{sum(r.boundary_present for r in records)}/{len(records)}"
    )
    print(
        "prompt_not_ready: "
        f"{sum(not r.prompt_ready for r in records)}"
    )


def _request_contract_rejects_question(
    fixture: dict[str, Any],
) -> bool:
    try:
        AIResearchPreviewRequest.model_validate(
            {
                "answer_mode": fixture["answer_mode"],
                "detail_level": fixture["detail_level"],
                "question": fixture["user_question"],
            }
        )
    except ValidationError:
        return True
    return False


def _structure_by_mode(records: list[AuditRecord]) -> str:
    grouped: dict[str, list[AuditRecord]] = defaultdict(list)
    for record in records:
        grouped[record.answer_mode].append(record)
    lines = [
        "| Answer mode | Complete | Total | Rate |",
        "|---|---:|---:|---:|",
    ]
    for mode, mode_records in sorted(grouped.items()):
        complete = sum(record.structure_complete for record in mode_records)
        lines.append(
            f"| `{mode}` | {complete} | {len(mode_records)} | "
            f"{_pct(_rate(complete, len(mode_records)))} |"
        )
    return "\n".join(lines)


def _citation_table(records: list[AuditRecord]) -> str:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record in records:
        for section in SECTION_KEYS:
            grouped[(record.answer_mode, section)].append(
                record.section_citations.get(section, 0)
            )
    lines = [
        "| Answer mode | Section | Avg context IDs | Min | Max |",
        "|---|---|---:|---:|---:|",
    ]
    for (mode, section), counts in sorted(grouped.items()):
        lines.append(
            f"| `{mode}` | `{section}` | {mean(counts):.2f} | "
            f"{min(counts)} | {max(counts)} |"
        )
    return "\n".join(lines)


def _mode_detail_table(records: list[AuditRecord]) -> str:
    grouped: dict[tuple[str, str], list[AuditRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.answer_mode, record.detail_level)].append(record)
    lines = [
        "| Answer mode | Detail | Runs | Ready false | Token estimate min/avg/max | Selected cards min/avg/max | Excluded constraints min/avg/max |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for (mode, detail), group in sorted(grouped.items()):
        tokens = [record.prompt_token_estimate for record in group]
        cards = [record.selected_card_count for record in group]
        constraints = [
            record.excluded_constraint_count for record in group
        ]
        lines.append(
            f"| `{mode}` | `{detail}` | {len(group)} | "
            f"{sum(not record.prompt_ready for record in group)} | "
            f"{_triple(tokens)} | {_triple(cards)} | "
            f"{_triple(constraints)} |"
        )
    return "\n".join(lines)


def _adversarial_table(records: list[AuditRecord]) -> str:
    lines = [
        "| Test ID | Mode | Contract rejected | Semantic blocker | Refusal boundary | Handled |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for record in sorted(records, key=lambda item: item.test_id):
        lines.append(
            f"| `{record.test_id}` | `{record.answer_mode}` | "
            f"{_yes_no(record.request_contract_rejected)} | "
            f"{_yes_no(record.semantic_blocked)} | "
            f"{_yes_no(record.refusal_boundary_present)} | "
            f"{_yes_no(record.adversarial_handled)} |"
        )
    return "\n".join(lines)


def _counter_table(counter: Counter[Any], label: str) -> str:
    if not counter:
        return f"| {label} | Count |\n|---|---:|\n| none | 0 |"
    lines = [f"| {label} | Count |", "|---|---:|"]
    for key, value in sorted(counter.items(), key=lambda item: str(item[0])):
        lines.append(f"| `{key}` | {value} |")
    return "\n".join(lines)


def _distribution_table(counter: Counter[int], label: str) -> str:
    lines = [f"| {label} | Fixture count |", "|---:|---:|"]
    for value, count in sorted(counter.items()):
        lines.append(f"| {value} | {count} |")
    return "\n".join(lines)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _triple(values: list[int]) -> str:
    return f"{min(values)}/{mean(values):.1f}/{max(values)}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
