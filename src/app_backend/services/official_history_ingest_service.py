from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from app_backend.services.official_history_ingest_guard import (
    OfficialHistoryAdmissionError,
    resolve_approved_history_route,
    validate_history_batch,
)

FredReader = Callable[[str, int], dict[str, Any]]
BlsWindowReader = Callable[[list[str], int, int], dict[str, Any]]
HistoryWriter = Callable[[list[dict[str, Any]]], Any]
NowProvider = Callable[[], str]


_FRED_RATE_SERIES: dict[str, dict[str, str]] = {
    "DGS2": {"metric_key": "dgs2", "unit": "percent", "freshness_policy": "business_daily"},
    "DGS10": {"metric_key": "dgs10", "unit": "percent", "freshness_policy": "business_daily"},
    "DGS30": {"metric_key": "dgs30", "unit": "percent", "freshness_policy": "business_daily"},
    "T10Y2Y": {
        "metric_key": "t10y2y",
        "unit": "percentage_points",
        "freshness_policy": "business_daily",
    },
    "T10YIE": {
        "metric_key": "t10yie",
        "unit": "percent",
        "freshness_policy": "business_daily",
    },
    "DFII10": {
        "metric_key": "dfii10",
        "unit": "percent",
        "freshness_policy": "business_daily",
    },
}

_BLS_CPI_SERIES: dict[str, dict[str, Any]] = {
    "CUSR0000SA0": {
        "index_metric_key": "headline_cpi_index",
        "yoy_metric_key": "headline_cpi_yoy",
        "expected_title_tokens": ("all items", "u.s. city average"),
    },
    "CUSR0000SA0L1E": {
        "index_metric_key": "core_cpi_index",
        "yoy_metric_key": "core_cpi_yoy",
        "expected_title_tokens": ("less food and energy", "u.s. city average"),
    },
}


@dataclass(frozen=True)
class OfficialHistoryIngestService:
    fred_reader: FredReader
    bls_window_reader: BlsWindowReader
    history_writer: HistoryWriter
    now_provider: NowProvider

    def run(
        self,
        route_key: str,
        *,
        live: bool = False,
        write: bool = False,
        fred_limit: int = 5000,
        start_year: int = 2000,
        end_year: int | None = None,
    ) -> dict[str, Any]:
        if write and not live:
            return _summary(
                route_key,
                status="blocked",
                live=live,
                write=write,
                error_codes=["write_requires_live"],
            )
        try:
            route = resolve_approved_history_route(route_key)
        except OfficialHistoryAdmissionError as exc:
            return _summary(
                route_key,
                status="blocked",
                live=live,
                write=write,
                error_codes=[exc.code],
            )
        if not live:
            return _summary(
                route_key,
                status="planned",
                live=False,
                write=False,
                error_codes=["live_disabled"],
                planned_series=[item.source_series for item in route.series],
                planned_metric_keys=[item.metric_key for item in route.series],
            )

        if fred_limit < 1:
            return _summary(
                route_key,
                status="blocked",
                live=live,
                write=write,
                error_codes=["invalid_fred_limit"],
            )

        if route_key == "fred_rates":
            observations, errors = self._fred_observations(fred_limit=fred_limit)
        elif route_key == "bls_cpi":
            observations, errors = self._bls_observations(
                start_year=start_year,
                end_year=end_year,
            )
        else:
            observations, errors = [], ["unsupported_route"]

        if errors:
            return _summary(
                route_key,
                status="blocked",
                live=live,
                write=write,
                error_codes=sorted(set(errors)),
            )

        if not _has_complete_required_series(route_key, observations):
            return _summary(
                route_key,
                status="blocked",
                live=live,
                write=write,
                normalized_observations=len(observations),
                error_codes=["missing_required_series"],
            )

        try:
            validated = list(validate_history_batch(route_key, observations))
        except OfficialHistoryAdmissionError as exc:
            return _summary(
                route_key,
                status="blocked",
                live=live,
                write=write,
                normalized_observations=len(observations),
                error_codes=[exc.code],
            )

        if not write:
            return _summary(
                route_key,
                status="dry_run",
                live=True,
                write=False,
                normalized_observations=len(validated),
                source_badge_distribution=_source_badge_distribution(validated),
                metric_kind_distribution=_metric_kind_distribution(validated),
            )

        try:
            write_result = self.history_writer(validated)
        except Exception:
            return _summary(
                route_key,
                status="blocked",
                live=True,
                write=True,
                normalized_observations=len(validated),
                error_codes=["write_failed"],
            )
        write_counts = _validated_writer_counts(write_result, expected_count=len(validated))
        if write_counts is None:
            return _summary(
                route_key,
                status="blocked",
                live=True,
                write=True,
                normalized_observations=len(validated),
                error_codes=["write_failed"],
            )
        inserted_count, updated_count = write_counts
        return _summary(
            route_key,
            status="written",
            live=True,
            write=True,
            normalized_observations=len(validated),
            inserted_count=inserted_count,
            updated_count=updated_count,
            source_badge_distribution=_source_badge_distribution(validated),
            metric_kind_distribution=_metric_kind_distribution(validated),
        )

    def _fred_observations(self, *, fred_limit: int) -> tuple[list[dict[str, Any]], list[str]]:
        ingested_at = self.now_provider()
        observations: list[dict[str, Any]] = []
        errors: list[str] = []
        for series_id, config in _FRED_RATE_SERIES.items():
            try:
                payload = self.fred_reader(series_id, fred_limit)
            except Exception:
                errors.append("provider_error")
                continue
            if not isinstance(payload, dict):
                errors.append("malformed_payload")
                continue
            if payload.get("status") != "ok":
                errors.append("provider_error")
                continue
            actual_series = str(payload.get("series_id") or series_id).upper()
            if actual_series != series_id:
                errors.append("series_mismatch")
                continue
            data = payload.get("data")
            if not isinstance(data, list):
                errors.append("malformed_payload")
                continue
            for item in data:
                if not isinstance(item, dict):
                    errors.append("malformed_payload")
                    continue
                row = _normalize_fred_item(
                    item,
                    series_id=series_id,
                    config=config,
                    ingested_at=ingested_at,
                    generated_at=str(payload.get("timestamp") or ingested_at),
                )
                if isinstance(row, str):
                    errors.append(row)
                else:
                    observations.append(row)
        return observations, errors

    def _bls_observations(
        self,
        *,
        start_year: int,
        end_year: int | None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        final_year = end_year if end_year is not None else _year_from_now(self.now_provider())
        try:
            chunks = _split_year_chunks(start_year, final_year)
        except ValueError:
            return [], ["invalid_year_range"]

        all_rows: dict[tuple[str, str], dict[str, Any]] = {}
        errors: list[str] = []
        for chunk_start, chunk_end in chunks:
            try:
                payload = self.bls_window_reader(list(_BLS_CPI_SERIES), chunk_start, chunk_end)
            except Exception:
                errors.append("provider_error")
                continue
            if not isinstance(payload, dict):
                errors.append("malformed_payload")
                continue
            if payload.get("status") != "ok":
                errors.append("provider_error")
                continue
            series_payloads = payload.get("series")
            if not isinstance(series_payloads, list):
                errors.append("malformed_payload")
                continue
            ingested_at = str(payload.get("retrieved_at") or self.now_provider())
            for series_payload in series_payloads:
                if not isinstance(series_payload, dict):
                    errors.append("malformed_payload")
                    continue
                normalized, row_errors = _normalize_bls_series(
                    series_payload,
                    ingested_at=ingested_at,
                )
                errors.extend(row_errors)
                for row in normalized:
                    all_rows[(row["series_id"], row["observation_date"])] = row
        if errors:
            return [], errors

        index_rows = sorted(
            all_rows.values(),
            key=lambda item: (item["series_id"], item["observation_date"]),
        )
        yoy_rows = _calculate_bls_yoy(index_rows)
        observations = [
            _build_bls_market_observation(row, derived=derived)
            for row, derived in [(row, False) for row in index_rows]
            + [(row, True) for row in yoy_rows]
        ]
        return observations, []


def build_default_official_history_ingest_service() -> OfficialHistoryIngestService:
    def fred_reader(series_id: str, limit: int) -> dict[str, Any]:
        from data_providers import fred_provider

        return fred_provider.get_fred_series(series_id, limit=limit)

    def bls_reader(series_ids: list[str], start_year: int, end_year: int) -> dict[str, Any]:
        from scripts import ingest_official_bls_cpi_history as bls_ingest

        return bls_ingest.fetch_bls_v1_window(series_ids, start_year, end_year)

    def writer(observations: list[dict[str, Any]]) -> dict[str, int]:
        from data_providers import market_history_store

        return market_history_store.upsert_market_observations(observations)

    return OfficialHistoryIngestService(
        fred_reader=fred_reader,
        bls_window_reader=bls_reader,
        history_writer=writer,
        now_provider=_utc_now,
    )


def _normalize_fred_item(
    item: dict[str, Any],
    *,
    series_id: str,
    config: dict[str, str],
    ingested_at: str,
    generated_at: str,
) -> dict[str, Any] | str:
    observation_date = str(item.get("date") or "").strip()
    if not _is_iso_date(observation_date):
        return "invalid_observation_date"
    value = _to_float_or_none(item.get("value"))
    if value is None:
        return "invalid_numeric_value"
    return {
        "metric_key": config["metric_key"],
        "observation_date": observation_date,
        "value": value,
        "value_text": str(value),
        "unit": config["unit"],
        "status": "ok",
        "source": "FRED",
        "source_badge": "official_fallback",
        "provider": "fred",
        "source_series": series_id,
        "generated_at": generated_at,
        "fetched_at": ingested_at,
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "raw",
        "lineage": {
            "provider": "fred",
            "source": "Federal Reserve Economic Data",
            "source_badge": "official_fallback",
            "source_series": series_id,
            "retrieval_method": "api",
            "freshness_policy": config["freshness_policy"],
            "ai_context_allowed": True,
            "trigger_eligibility": "eligible",
            "ingested_at": ingested_at,
            "metric_key": config["metric_key"],
            "source_priority": "official_fallback",
        },
    }


def _normalize_bls_series(
    series_payload: dict[str, Any],
    *,
    ingested_at: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    series_id = str(series_payload.get("seriesID") or "")
    if series_id not in _BLS_CPI_SERIES:
        return [], ["series_mismatch"]
    title_validation = _validate_bls_title(series_id, series_payload)
    if title_validation is None:
        return [], ["title_mismatch"]
    data = series_payload.get("data")
    if not isinstance(data, list):
        return [], ["malformed_payload"]
    config = _BLS_CPI_SERIES[series_id]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            errors.append("malformed_payload")
            continue
        period = str(item.get("period") or "")
        year = str(item.get("year") or "")
        if period == "M13":
            continue
        if not period.startswith("M") or not year.isdigit():
            errors.append("invalid_observation_date")
            continue
        try:
            month = int(period[1:])
        except ValueError:
            errors.append("invalid_observation_date")
            continue
        if not 1 <= month <= 12:
            errors.append("invalid_observation_date")
            continue
        value = _to_float_or_none(str(item.get("value") or "").replace(",", ""))
        if value is None:
            errors.append("invalid_numeric_value")
            continue
        rows.append(
            {
                "series_id": series_id,
                "metric_key": config["index_metric_key"],
                "observation_date": f"{year}-{month:02d}-01",
                "value": value,
                "title_validation": title_validation,
                "ingested_at": ingested_at,
            }
        )
    rows.sort(key=lambda item: item["observation_date"])
    return rows, errors


def _validate_bls_title(series_id: str, series_payload: dict[str, Any]) -> str | None:
    returned_id = str(series_payload.get("seriesID") or "")
    if returned_id != series_id:
        return None
    catalog = series_payload.get("catalog")
    title = ""
    if isinstance(catalog, dict):
        title = str(catalog.get("series_title") or catalog.get("seriesTitle") or "")
    if not title:
        title = str(series_payload.get("seriesTitle") or "")
    if not title:
        return "series_registry_confirmed_response_id"
    lowered = title.lower()
    expected_tokens = _BLS_CPI_SERIES[series_id]["expected_title_tokens"]
    return "response_title_confirmed" if all(token in lowered for token in expected_tokens) else None


def _calculate_bls_yoy(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_series: dict[str, dict[str, dict[str, Any]]] = {}
    for row in records:
        by_series.setdefault(row["series_id"], {})[row["observation_date"]] = row
    output: list[dict[str, Any]] = []
    for series_id, dated in by_series.items():
        for observation_date, row in sorted(dated.items()):
            year, month, _ = (int(part) for part in observation_date.split("-"))
            prior_date = f"{year - 1:04d}-{month:02d}-01"
            prior = dated.get(prior_date)
            if not prior or float(prior["value"]) == 0:
                continue
            output.append(
                {
                    **row,
                    "metric_key": _BLS_CPI_SERIES[series_id]["yoy_metric_key"],
                    "value": (float(row["value"]) / float(prior["value"]) - 1.0) * 100.0,
                    "prior_observation_date": prior_date,
                }
            )
    return output


def _build_bls_market_observation(row: dict[str, Any], *, derived: bool) -> dict[str, Any]:
    lineage = {
        "provider": "bls",
        "source": "U.S. Bureau of Labor Statistics",
        "source_badge": "official",
        "source_series": row["series_id"],
        "retrieval_method": "api_v1_post",
        "freshness_policy": "monthly_release",
        "ai_context_allowed": True,
        "trigger_eligibility": "eligible",
        "ingested_at": row["ingested_at"],
        "title_validation": row["title_validation"],
        "source_priority": "primary_over_fred",
    }
    if derived:
        lineage["derivation"] = "year_over_year_percent_change"
        lineage["prior_observation_date"] = row["prior_observation_date"]
    return {
        "metric_key": row["metric_key"],
        "observation_date": row["observation_date"],
        "value": row["value"],
        "value_text": f"{row['value']:.4f}" if derived else str(row["value"]),
        "unit": "percent_yoy" if derived else "index",
        "status": "ok",
        "source": "BLS",
        "source_badge": "official",
        "provider": "bls",
        "source_series": row["series_id"],
        "fetched_at": row["ingested_at"],
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "derived" if derived else "raw",
        "lineage": lineage,
    }


def _split_year_chunks(start_year: int, end_year: int, size: int = 10) -> list[tuple[int, int]]:
    if start_year > end_year:
        raise ValueError("start_year_must_not_exceed_end_year")
    if size < 1 or size > 10:
        raise ValueError("bls_window_size_must_be_1_to_10")
    chunks = []
    cursor = start_year
    while cursor <= end_year:
        chunk_end = min(cursor + size - 1, end_year)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return chunks


def _summary(
    route_key: str,
    *,
    status: str,
    live: bool,
    write: bool,
    error_codes: list[str] | None = None,
    normalized_observations: int = 0,
    inserted_count: int = 0,
    updated_count: int = 0,
    planned_series: list[str] | None = None,
    planned_metric_keys: list[str] | None = None,
    source_badge_distribution: dict[str, int] | None = None,
    metric_kind_distribution: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "route_key": route_key,
        "status": status,
        "live": live,
        "write": write,
        "error_codes": error_codes or [],
        "normalized_observations": normalized_observations,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "planned_series": planned_series or [],
        "planned_metric_keys": planned_metric_keys or [],
        "source_badge_distribution": source_badge_distribution or {},
        "metric_kind_distribution": metric_kind_distribution or {},
    }


def _source_badge_distribution(observations: list[dict[str, Any]]) -> dict[str, int]:
    return _count_by_key(observations, "source_badge")


def _metric_kind_distribution(observations: list[dict[str, Any]]) -> dict[str, int]:
    return _count_by_key(observations, "metric_kind")


def _has_complete_required_series(route_key: str, observations: list[dict[str, Any]]) -> bool:
    if route_key == "fred_rates":
        required = set(_FRED_RATE_SERIES)
    elif route_key == "bls_cpi":
        required = set(_BLS_CPI_SERIES)
    else:
        return False
    present = {
        str(item.get("source_series") or "")
        for item in observations
        if item.get("metric_kind") == "raw"
    }
    return required <= present


def _validated_writer_counts(result: Any, *, expected_count: int) -> tuple[int, int] | None:
    if not isinstance(result, dict):
        return None
    required_keys = ("observation_count", "inserted_count", "updated_count")
    if any(key not in result for key in required_keys):
        return None
    counts = [result[key] for key in required_keys]
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
        return None
    observation_count, inserted_count, updated_count = counts
    if observation_count != expected_count:
        return None
    if inserted_count + updated_count != expected_count:
        return None
    return inserted_count, updated_count


def _count_by_key(observations: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in observations:
        value = str(item.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _to_float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == ".":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and numeric not in {float("inf"), float("-inf")} else None


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _year_from_now(value: str) -> int:
    return datetime.fromisoformat(value).year


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "OfficialHistoryIngestService",
    "build_default_official_history_ingest_service",
]
