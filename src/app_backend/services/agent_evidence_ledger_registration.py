"""Register sanitized agent tool results into a run-scoped evidence ledger."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app_backend.services.agent_tool_registry import ToolResult
from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
    sha256_json_summary,
)


@dataclass(frozen=True)
class ToolEvidenceRegistration:
    ledger: RunEvidenceLedger
    result: ToolResult
    evidence_ids: list[str]
    evidence_tiers: list[str]


def register_tool_result_evidence(
    ledger: RunEvidenceLedger,
    *,
    tool_name: str,
    result: ToolResult,
) -> ToolEvidenceRegistration:
    """Register evidence from a sanitized successful tool result."""
    if result.status != "ok":
        return ToolEvidenceRegistration(ledger=ledger, result=result, evidence_ids=[], evidence_tiers=[])
    records, content = _records_from_content(
        run_id=ledger.run_id,
        tool_name=tool_name,
        content=result.content,
    )
    if not records:
        return ToolEvidenceRegistration(ledger=ledger, result=result, evidence_ids=[], evidence_tiers=[])

    updated = ledger
    existing = set(updated.by_id())
    evidence_ids: list[str] = []
    evidence_tiers: list[str] = []
    for record in records:
        evidence_ids.append(record.evidence_id)
        evidence_tiers.append(record.evidence_tier)
        if record.evidence_id in existing:
            continue
        try:
            updated = updated.add(record)
        except ValueError:
            continue
        existing.add(record.evidence_id)

    augmented = _with_registered_ids(content, evidence_ids)
    return ToolEvidenceRegistration(
        ledger=updated,
        result=ToolResult(status=result.status, content=augmented),
        evidence_ids=evidence_ids,
        evidence_tiers=evidence_tiers,
    )


def _records_from_content(
    *,
    run_id: str,
    tool_name: str,
    content: Any,
) -> tuple[list[EvidenceRecord], Any]:
    if not isinstance(content, dict):
        return [], content
    if tool_name == "rag_retrieve":
        return _records_from_rag(run_id, tool_name, content)
    if tool_name == "search_tavily":
        return _records_from_search(run_id, tool_name, content)
    if tool_name == "quote_etf":
        return _records_from_quote_etf(run_id, tool_name, content)
    if tool_name == "treasury_curve":
        return _records_from_treasury_curve(run_id, tool_name, content)
    if tool_name == "quote_dxy":
        return _records_from_dxy(run_id, tool_name, content)
    if tool_name == "commodity_quote":
        return _records_from_commodity(run_id, tool_name, content)
    if tool_name == "evidence_lookup":
        return _records_from_evidence_rows(run_id, tool_name, content)
    if tool_name == "dashboard_query":
        return _record_from_dashboard(run_id, tool_name, content)
    return [], content


def _records_from_rag(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    chunks = content.get("chunks")
    if not isinstance(chunks, list):
        return [], content
    records: list[EvidenceRecord] = []
    rendered: list[Any] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            rendered.append(chunk)
            continue
        evidence_tier = _evidence_tier_for_rag(chunk)
        source_kind = (
            "institutional_research"
            if evidence_tier == "institutional_view"
            else "official_primary"
        )
        record = _record(
            run_id=run_id,
            tool_name=tool_name,
            source_kind=source_kind,
            evidence_tier=evidence_tier,
            title=_text(chunk.get("title")) or "RAG retrieved chunk",
            rag_doc_id=_text(chunk.get("doc_id")),
            observation_date=_date_prefix(chunk.get("observation_period")),
            release_date=_date_prefix(chunk.get("release_date")),
            temporal_status="reported" if evidence_tier == "institutional_view" else "as_released",
            value_summary={
                "doc_type": _text(chunk.get("doc_type")),
                "chunk_index": chunk.get("chunk_index"),
                "source_domain": _text(chunk.get("source_domain")),
                "observation_period": _text(chunk.get("observation_period")),
                "release_date": _text(chunk.get("release_date")),
                "vintage": _text(chunk.get("vintage")),
            },
            payload=chunk,
        )
        if record is None:
            rendered.append(chunk)
            continue
        records.append(record)
        rendered.append({**chunk, "evidence_id": record.evidence_id})
    return records, {**content, "chunks": rendered}


def _records_from_search(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    results = content.get("results")
    if not isinstance(results, list):
        return [], content
    records: list[EvidenceRecord] = []
    rendered: list[Any] = []
    for item in results:
        if not isinstance(item, dict):
            rendered.append(item)
            continue
        record = _record(
            run_id=run_id,
            tool_name=tool_name,
            source_kind="public_reporting",
            evidence_tier="public_reporting",
            title=_text(item.get("title")) or _text(item.get("url")) or "Search result",
            canonical_url=_text(item.get("url")),
            observation_date=_date_prefix(item.get("published_at")),
            temporal_status="reported",
            value_summary={
                "domain": _text(item.get("domain")),
                "relevance_score": item.get("relevance_score"),
            },
            payload=item,
            public_visible=True,
        )
        if record is None:
            rendered.append(item)
            continue
        records.append(record)
        rendered.append({**item, "evidence_id": record.evidence_id})
    return records, {**content, "results": rendered}


def _records_from_quote_etf(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    quotes = content.get("quotes")
    if not isinstance(quotes, list):
        return [], content
    records: list[EvidenceRecord] = []
    rendered: list[Any] = []
    for quote in quotes:
        if not isinstance(quote, dict) or quote.get("value") is None:
            rendered.append(quote)
            continue
        symbol = _text(quote.get("symbol")) or "ETF"
        record = _local_data_record(
            run_id=run_id,
            tool_name=tool_name,
            title=f"ETF quote {symbol}",
            series_id=symbol,
            observation_date=_date_prefix(quote.get("observation_date")),
            payload=quote,
            value_summary={
                "symbol": symbol,
                "value": quote.get("value"),
                "unit": quote.get("unit"),
                "status": quote.get("status"),
            },
            atomic_observation=_atomic_observation(
                value=quote.get("value"),
                unit=quote.get("unit"),
                as_of=_date_prefix(quote.get("observation_date")),
                series_id=symbol,
            ),
        )
        if record is None:
            rendered.append(quote)
            continue
        records.append(record)
        rendered.append({**quote, "evidence_id": record.evidence_id})
    return records, {**content, "quotes": rendered}


def _records_from_treasury_curve(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    points = content.get("points")
    if not isinstance(points, list):
        return [], content
    records: list[EvidenceRecord] = []
    rendered: list[Any] = []
    for point in points:
        if not isinstance(point, dict) or point.get("value") is None:
            rendered.append(point)
            continue
        series_id = _text(point.get("source_series")) or _text(point.get("series_id"))
        title = f"Treasury curve {point.get('tenor') or series_id or 'point'}"
        record = _local_data_record(
            run_id=run_id,
            tool_name=tool_name,
            title=title,
            series_id=series_id,
            canonical_url=_fred_url(series_id),
            observation_date=_date_prefix(point.get("observation_date")),
            payload=point,
            value_summary={
                "tenor": _text(point.get("tenor")),
                "value": point.get("value"),
                "unit": point.get("unit") or "%",
                "status": point.get("status"),
            },
            atomic_observation=_atomic_observation(
                value=point.get("value"),
                unit=point.get("unit") or "%",
                as_of=_date_prefix(point.get("observation_date")),
                series_id=series_id,
            ),
        )
        if record is None:
            rendered.append(point)
            continue
        records.append(record)
        rendered.append({**point, "evidence_id": record.evidence_id})
    return records, {**content, "points": rendered}


def _records_from_dxy(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    if content.get("status") != "ok" or content.get("value") is None:
        return [], content
    series_id = _text(content.get("series_id")) or "DTWEXBGS"
    record = _local_data_record(
        run_id=run_id,
        tool_name=tool_name,
        title=_text(content.get("name")) or "Broad trade-weighted USD index",
        series_id=series_id,
        canonical_url=_fred_url(series_id),
        observation_date=_date_prefix(content.get("observation_date")),
        payload=content,
        value_summary={
            "series_id": series_id,
            "value": content.get("value"),
            "unit": content.get("unit"),
            "status": content.get("status"),
        },
        atomic_observation=_atomic_observation(
            value=content.get("value"),
            unit=content.get("unit"),
            as_of=_date_prefix(content.get("observation_date")),
            series_id=series_id,
        ),
    )
    if record is None:
        return [], content
    return [record], {**content, "evidence_id": record.evidence_id}


def _records_from_commodity(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    if content.get("status") != "observed" or content.get("value_usd_per_barrel") is None:
        return [], content
    benchmark = _text(content.get("benchmark")) or "commodity"
    record = _record(
        run_id=run_id,
        tool_name=tool_name,
        source_kind="public_reporting",
        evidence_tier="public_reporting",
        title=_text(content.get("source_title")) or f"Commodity quote {benchmark}",
        canonical_url=_text(content.get("source_url")),
        temporal_status="reported",
        value_summary={
            "benchmark": benchmark,
            "value_usd_per_barrel": content.get("value_usd_per_barrel"),
            "unit": content.get("unit"),
        },
        atomic_observations=_atomic_observations(
            value=content.get("value_usd_per_barrel"),
            unit=content.get("unit"),
            as_of=_date_prefix(content.get("observed_at") or content.get("as_of")),
            series_id=benchmark,
        ),
        payload=content,
        public_visible=True,
    )
    if record is None:
        return [], content
    return [record], {**content, "evidence_id": record.evidence_id}


def _records_from_evidence_rows(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    rows = content.get("rows")
    if not isinstance(rows, list):
        return [], content
    records: list[EvidenceRecord] = []
    rendered: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            rendered.append(row)
            continue
        metric_key = _text(row.get("metric_key")) or _text(row.get("module_key"))
        record = _local_data_record(
            run_id=run_id,
            tool_name=tool_name,
            title=f"Dashboard evidence {metric_key or 'row'}",
            series_id=metric_key,
            observation_date=_date_prefix(row.get("observation_date") or row.get("as_of")),
            payload=row,
            value_summary={
                "module_key": _text(row.get("module_key")),
                "metric_key": _text(row.get("metric_key")),
                "value": row.get("value"),
                "unit": row.get("unit"),
            },
            atomic_observation=_atomic_observation(
                value=row.get("value"),
                unit=row.get("unit"),
                as_of=_date_prefix(row.get("observation_date") or row.get("as_of")),
                series_id=metric_key,
            ),
        )
        if record is None:
            rendered.append(row)
            continue
        records.append(record)
        rendered.append({**row, "evidence_id": record.evidence_id})
    return records, {**content, "rows": rendered}


def _record_from_dashboard(
    run_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    record = _local_data_record(
        run_id=run_id,
        tool_name=tool_name,
        title="Dashboard summary",
        series_id=_text(content.get("series")),
        observation_date=_date_prefix(content.get("observation_date") or content.get("as_of")),
        payload=content,
        value_summary={key: content.get(key) for key in ("series", "value", "overall_status") if key in content},
        atomic_observation=_atomic_observation(
            value=content.get("value"),
            unit=content.get("unit"),
            as_of=_date_prefix(content.get("observation_date") or content.get("as_of")),
            series_id=_text(content.get("series")),
        ),
    )
    if record is None:
        return [], content
    return [record], {**content, "evidence_id": record.evidence_id}


def _local_data_record(
    *,
    run_id: str,
    tool_name: str,
    title: str,
    payload: dict[str, Any],
    value_summary: dict[str, Any],
    series_id: str | None = None,
    canonical_url: str | None = None,
    observation_date: str | None = None,
    atomic_observation: AtomicObservation | None = None,
) -> EvidenceRecord | None:
    return _record(
        run_id=run_id,
        tool_name=tool_name,
        source_kind="local_data_foundation",
        evidence_tier="local_data_foundation",
        title=title,
        canonical_url=canonical_url,
        series_id=series_id,
        observation_date=observation_date,
        release_date=observation_date,
        temporal_status="observed",
        value_summary=value_summary,
        payload=payload,
        atomic_observations=(atomic_observation,) if atomic_observation is not None else (),
    )


def _record(
    *,
    run_id: str,
    tool_name: str,
    source_kind: str,
    evidence_tier: str,
    title: str,
    payload: dict[str, Any],
    value_summary: dict[str, Any],
    canonical_url: str | None = None,
    rag_doc_id: str | None = None,
    series_id: str | None = None,
    observation_date: str | None = None,
    release_date: str | None = None,
    temporal_status: str = "observed",
    public_visible: bool = False,
    atomic_observations: tuple[AtomicObservation, ...] = (),
) -> EvidenceRecord | None:
    evidence_id = _evidence_id(tool_name, payload)
    try:
        return EvidenceRecord(
            evidence_id=evidence_id,
            run_id=run_id,
            tool_name=tool_name,
            source_kind=source_kind,
            evidence_tier=evidence_tier,
            title=title,
            canonical_url=canonical_url,
            rag_doc_id=rag_doc_id,
            series_id=series_id,
            observation_date=observation_date,
            release_date=release_date,
            temporal_status=temporal_status,
            value_summary={key: value for key, value in value_summary.items() if value is not None},
            atomic_observations=atomic_observations,
            content_sha256=sha256_json_summary(payload),
            public_visible=public_visible,
        )
    except ValidationError:
        return None


def _evidence_id(tool_name: str, payload: dict[str, Any]) -> str:
    digest = sha256_json_summary({"tool_name": tool_name, "payload": payload})[:16]
    return f"ev_{tool_name}_{digest}"[:128]


def _atomic_observation(
    *,
    value: Any,
    unit: Any = None,
    as_of: str | None = None,
    series_id: str | None = None,
) -> AtomicObservation | None:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    unit_text = _text(unit)
    try:
        return AtomicObservation(
            value=value,
            unit=unit_text,
            as_of=as_of,
            series_id=series_id,
        )
    except ValidationError:
        return None


def _atomic_observations(
    *,
    value: Any,
    unit: Any = None,
    as_of: str | None = None,
    series_id: str | None = None,
) -> tuple[AtomicObservation, ...]:
    observation = _atomic_observation(
        value=value,
        unit=unit,
        as_of=as_of,
        series_id=series_id,
    )
    return (observation,) if observation is not None else ()


def _with_registered_ids(content: Any, evidence_ids: list[str]) -> Any:
    if not isinstance(content, dict):
        return content
    return {**content, "registered_evidence_ids": evidence_ids}


def _evidence_tier_for_rag(chunk: dict[str, Any]) -> str:
    tier = chunk.get("evidence_tier")
    if tier == "institutional_view":
        return "institutional_view"
    return "official_evidence"


def _fred_url(series_id: str | None) -> str | None:
    if not series_id:
        return None
    return f"https://fred.stlouisfed.org/series/{series_id}"


def _date_prefix(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text[:10] if len(text) >= 10 else text


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


__all__ = [
    "ToolEvidenceRegistration",
    "register_tool_result_evidence",
]
