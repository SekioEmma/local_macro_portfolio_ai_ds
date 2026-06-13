from __future__ import annotations

from dataclasses import dataclass

from app_backend.schemas.responses import (
    DashboardEvidenceTableResponse,
    DashboardSummaryResponse,
)


@dataclass
class DashboardPipelineContext:
    summary: DashboardSummaryResponse | None = None
    evidence_table: DashboardEvidenceTableResponse | None = None
