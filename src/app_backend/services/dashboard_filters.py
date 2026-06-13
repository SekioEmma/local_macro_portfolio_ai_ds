from __future__ import annotations

from app_backend.schemas.responses import DashboardEvidenceRow


def evidence_row_matches(
    row: DashboardEvidenceRow,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> bool:
    if module is not None and row.module != module:
        return False
    if status is not None and row.status != status:
        return False
    if source_badge is not None and row.source_badge != source_badge:
        return False
    if ai_context_allowed is not None and row.ai_context_allowed != ai_context_allowed:
        return False
    return True


def apply_evidence_filters(
    rows: list[DashboardEvidenceRow],
    *,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> list[DashboardEvidenceRow]:
    return [
        row
        for row in rows
        if evidence_row_matches(
            row,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        )
    ]
