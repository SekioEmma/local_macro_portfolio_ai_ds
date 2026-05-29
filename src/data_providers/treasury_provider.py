from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree


SOURCE = "U.S. Treasury"
SOURCE_TIER = "official_fallback"
TREASURY_YIELD_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
)
DEFINITION_NOTE = "Daily Treasury Par Yield Curve Rate; not FRED DGS constant maturity yield."
MATURITY_FIELDS = {
    "2y": ("BC_2YEAR", "2 Yr"),
    "10y": ("BC_10YEAR", "10 Yr"),
    "30y": ("BC_30YEAR", "30 Yr"),
}
ATOM_NS = "{http://www.w3.org/2005/Atom}"
DATA_NS = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
METADATA_NS = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"


def get_par_yield(maturity: str) -> dict:
    generated_at = _utc_now()
    field_info = MATURITY_FIELDS.get(maturity)
    if field_info is None:
        return _yield_error(
            maturity=maturity,
            error=f"Unsupported Treasury maturity: {maturity}",
            timestamp=generated_at,
        )

    field_name, display_name = field_info
    try:
        import requests
    except ImportError as exc:
        return _yield_error(
            maturity=maturity,
            error=f"requests import failed: {exc}",
            timestamp=generated_at,
        )

    params = {
        "data": "daily_treasury_yield_curve",
        "field_tdr_date_value": str(datetime.now(timezone.utc).year),
    }
    try:
        response = requests.get(TREASURY_YIELD_XML_URL, params=params, timeout=20)
    except Exception as exc:
        return _yield_error(
            maturity=maturity,
            error=f"Treasury request failed: {exc}",
            timestamp=generated_at,
        )

    if response.status_code != 200:
        return _yield_error(
            maturity=maturity,
            error=f"Treasury HTTP status {response.status_code}: {_text_preview(response.text)}",
            timestamp=generated_at,
        )

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError as exc:
        return _yield_error(
            maturity=maturity,
            error=f"Treasury XML parse failed: {exc}",
            timestamp=generated_at,
        )

    latest = _latest_value(root, field_name)
    if latest is None:
        return _yield_error(
            maturity=maturity,
            error=f"Treasury XML missing parseable {display_name} rate",
            timestamp=generated_at,
        )

    observation_date, value = latest
    return {
        "value": value,
        "observation_date": observation_date,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "ok",
        "error": None,
        "timestamp": generated_at,
        "fallback_series": f"Daily Treasury Par Yield Curve Rate {display_name}",
        "definition_note": DEFINITION_NOTE,
    }


def _latest_value(root: ElementTree.Element, field_name: str) -> tuple[str, float] | None:
    records = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        properties = entry.find(f".//{METADATA_NS}properties")
        if properties is None:
            continue
        date_text = _child_text(properties, "NEW_DATE")
        value = _to_float_or_none(_child_text(properties, field_name))
        if not date_text or value is None:
            continue
        records.append((_normalize_date(date_text), value))

    if not records:
        return None
    records.sort(key=lambda item: item[0])
    return records[-1]


def _child_text(parent: ElementTree.Element, local_name: str) -> str | None:
    child = parent.find(f"{DATA_NS}{local_name}")
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _normalize_date(value: str) -> str:
    text = value.strip()
    if "T" in text:
        return text.split("T", 1)[0]
    return text


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _yield_error(maturity: str, error: str, timestamp: str) -> dict:
    return {
        "value": None,
        "observation_date": None,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "status": "error",
        "error": error,
        "timestamp": timestamp,
        "fallback_series": f"Daily Treasury Par Yield Curve Rate {maturity}",
        "definition_note": DEFINITION_NOTE,
    }


def _text_preview(text: str) -> str:
    return str(text).replace("\n", " ")[:200]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
