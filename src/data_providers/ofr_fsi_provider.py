from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


OFR_FSI_PAGE_URL = "https://www.financialresearch.gov/financial-stress-index/"
OFR_FSI_FALLBACK_URL = (
    "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
)
OFR_FSI_COLUMNS = {
    "OFR FSI": "ofr_fsi_total",
    "Credit": "ofr_fsi_credit",
    "Equity valuation": "ofr_fsi_equity_valuation",
    "Funding": "ofr_fsi_funding",
    "Safe assets": "ofr_fsi_safe_assets",
    "Volatility": "ofr_fsi_volatility",
    "United States": "ofr_fsi_united_states",
    "Other advanced economies": "ofr_fsi_other_advanced_economies",
    "Emerging markets": "ofr_fsi_emerging_markets",
}


def discover_download_url(
    html: str, *, page_url: str = OFR_FSI_PAGE_URL
) -> str | None:
    candidates = re.findall(
        r"""(?:href|action)\s*=\s*["']([^"']+)["']""",
        html,
        flags=re.IGNORECASE,
    )
    for candidate in candidates:
        lowered = candidate.lower()
        if "financial-stress-index" in lowered and lowered.endswith(".csv"):
            url = urljoin(page_url, candidate)
            if _is_official_ofr_url(url):
                return url
    return None


def fetch_text(url: str) -> dict[str, Any]:
    if not _is_official_ofr_url(url):
        raise ValueError("ofr_download_requires_financialresearch_gov_host")
    try:
        import requests
    except ImportError as exc:
        return {"status": "error", "error": f"requests import failed:{exc}"}
    try:
        response = requests.get(
            url,
            timeout=45,
            headers={"User-Agent": "local-macro-portfolio-ai/official-reference"},
        )
    except Exception as exc:
        return {"status": "error", "error": f"request_failed:{exc.__class__.__name__}"}
    if response.status_code != 200:
        return {"status": "error", "error": f"http_status:{response.status_code}"}
    return {
        "status": "ok",
        "text": response.text,
        "content": response.content,
        "last_modified": response.headers.get("Last-Modified"),
        "retrieved_at": _utc_now(),
        "url": url,
    }


def load_csv_source(
    *, file_path: Path | None = None, url: str | None = None
) -> dict[str, Any]:
    if bool(file_path) == bool(url):
        raise ValueError("provide_exactly_one_of_file_path_or_url")
    if file_path is not None:
        resolved = file_path.resolve()
        content = resolved.read_bytes()
        return {
            "status": "ok",
            "content": content,
            "url": str(resolved),
            "retrieval_method": "local_file",
            "last_modified": datetime.fromtimestamp(
                resolved.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "retrieved_at": _utc_now(),
            "raw_payload_hash": hashlib.sha256(content).hexdigest(),
        }
    assert url is not None
    result = fetch_text(url)
    if result.get("status") != "ok":
        return result
    content = result["content"]
    return {
        **result,
        "retrieval_method": "controlled_download",
        "raw_payload_hash": hashlib.sha256(content).hexdigest(),
    }


def parse_fsi_csv(content: bytes, *, ingested_at: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not reader.fieldnames or "Date" not in reader.fieldnames:
        raise ValueError("ofr_fsi_csv_missing_date")
    missing = sorted(set(OFR_FSI_COLUMNS) - set(reader.fieldnames))
    if missing:
        raise ValueError(f"ofr_fsi_csv_missing_columns:{','.join(missing)}")
    observations = []
    for row in reader:
        observation_date = str(row.get("Date") or "").strip()
        try:
            datetime.fromisoformat(observation_date)
        except ValueError:
            continue
        for column, metric_key in OFR_FSI_COLUMNS.items():
            value = _to_float_or_none(row.get(column))
            if value is None:
                continue
            observations.append(
                {
                    "metric_key": metric_key,
                    "source_series": column,
                    "observation_date": observation_date,
                    "value": value,
                    "ingested_at": ingested_at,
                }
            )
    observations.sort(
        key=lambda item: (item["metric_key"], item["observation_date"])
    )
    return observations


def _is_official_ofr_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "financialresearch.gov" or host.endswith(
        ".financialresearch.gov"
    )


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
