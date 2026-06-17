"""Evidence table assembly helpers extracted from dashboard_service.

Pure construction of DashboardEvidenceTableResponse from rows and summary,
plus filter metadata and unfiltered-request detection. These functions are
behavior-preserving extractions; they do not change row ordering, module
sorting, or filter semantics.
"""

from __future__ import annotations

from typing import Any

from app_backend.schemas.responses import (
    DashboardEvidenceRow,
    DashboardEvidenceTableResponse,
    DashboardSummaryResponse,
)
from app_backend.services.dashboard_evidence_policy import (
    build_evidence_row,
)
from app_backend.services.dashboard_filters import apply_evidence_filters


def evidence_request_is_unfiltered(
    *,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> bool:
    return (
        module is None
        and status is None
        and source_badge is None
        and ai_context_allowed is None
    )


def evidence_rows_from_summary(
    summary: DashboardSummaryResponse,
) -> list[DashboardEvidenceRow]:
    rows: list[DashboardEvidenceRow] = []
    for module_key, module in summary.modules.items():
        for metric in module.key_metrics:
            rows.append(build_evidence_row(module_key, metric))
    return rows


def evidence_filters(
    rows: list[DashboardEvidenceRow],
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> dict[str, Any]:
    return {
        "available": {
            "modules": sorted({row.module for row in rows}),
            "statuses": sorted({row.status for row in rows}),
            "source_badges": sorted({row.source_badge for row in rows}),
            "ai_context_allowed": sorted({row.ai_context_allowed for row in rows}),
        },
        "applied": {
            "module": module,
            "status": status,
            "source_badge": source_badge,
            "ai_context_allowed": ai_context_allowed,
        },
    }


def build_evidence_table_response(
    *,
    summary: DashboardSummaryResponse,
    all_rows: list[DashboardEvidenceRow],
    filtered_rows: list[DashboardEvidenceRow],
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> DashboardEvidenceTableResponse:
    return DashboardEvidenceTableResponse(
        generated_at=summary.generated_at,
        overall_status=summary.overall_status,
        row_count=len(filtered_rows),
        modules=sorted({row.module for row in all_rows}),
        rows=filtered_rows,
        filters=evidence_filters(
            all_rows,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        ),
        next_actions=summary.next_actions,
    )


def evidence_table_from_unfiltered(
    unfiltered_evidence_table: DashboardEvidenceTableResponse,
    *,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> DashboardEvidenceTableResponse:
    all_rows = list(unfiltered_evidence_table.rows)
    filtered_rows = apply_evidence_filters(
        all_rows,
        module=module,
        status=status,
        source_badge=source_badge,
        ai_context_allowed=ai_context_allowed,
    )
    return DashboardEvidenceTableResponse(
        generated_at=unfiltered_evidence_table.generated_at,
        overall_status=unfiltered_evidence_table.overall_status,
        row_count=len(filtered_rows),
        modules=sorted({row.module for row in all_rows}),
        rows=filtered_rows,
        filters=evidence_filters(
            all_rows,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        ),
        next_actions=list(unfiltered_evidence_table.next_actions),
    )
