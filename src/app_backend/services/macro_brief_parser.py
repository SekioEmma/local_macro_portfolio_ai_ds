"""Parse Phase F MacroBrief payloads into the strict Pydantic contract."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app_backend.schemas.macro_brief import MacroBrief, decode_findings


JsonObject = Mapping[str, Any]
JsonPayload = str | bytes | bytearray | JsonObject


class MacroBriefValidationError(ValueError):
    """Unified parser error for JSON parsing and MacroBrief validation."""

    def __init__(
        self,
        *,
        missing: list[str] | None = None,
        errors: list[str] | None = None,
        findings: list[str] | None = None,
    ) -> None:
        self.missing = tuple(missing or [])
        self.errors = tuple(errors or [])
        self.findings = tuple(findings or [])
        super().__init__(self._message())

    @property
    def all_issues(self) -> tuple[str, ...]:
        return (*self.missing, *self.errors, *self.findings)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "missing": list(self.missing),
            "errors": list(self.errors),
            "findings": list(self.findings),
        }

    def _message(self) -> str:
        counts = []
        if self.missing:
            counts.append(f"missing={len(self.missing)}")
        if self.errors:
            counts.append(f"errors={len(self.errors)}")
        if self.findings:
            counts.append(f"findings={len(self.findings)}")
        suffix = ", ".join(counts) if counts else "unknown"
        return f"MacroBrief validation failed ({suffix})"


def parse_macro_brief(payload: JsonPayload) -> MacroBrief:
    data = _normalize_macro_brief_payload(_load_json_object(payload))
    try:
        return MacroBrief.model_validate(data)
    except ValidationError as exc:
        missing, errors, findings = _split_validation_errors(exc)
        raise MacroBriefValidationError(
            missing=missing,
            errors=errors,
            findings=findings,
        ) from exc


def _load_json_object(payload: JsonPayload) -> JsonObject:
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, bytes | bytearray):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MacroBriefValidationError(
                errors=["json.invalid_utf8"]
            ) from exc
    if not isinstance(payload, str):
        raise MacroBriefValidationError(
            errors=[f"json.unsupported_payload_type:{type(payload).__name__}"]
        )

    text = payload.strip()
    if not text:
        raise MacroBriefValidationError(errors=["json.empty_payload"])
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MacroBriefValidationError(
            errors=[f"json.invalid:{exc.lineno}:{exc.colno}"]
        ) from exc
    if not isinstance(decoded, Mapping):
        raise MacroBriefValidationError(errors=["json.expected_object"])
    return decoded


def _normalize_macro_brief_payload(payload: JsonObject) -> dict[str, Any]:
    data = dict(payload)
    market_state = data.get("market_state")
    if isinstance(market_state, list):
        data["market_state"] = [
            _normalize_market_state_card(card) for card in market_state
        ]
    judgments = data.get("judgments")
    if isinstance(judgments, list):
        data["judgments"] = [_normalize_judgment(judgment) for judgment in judgments]
    source_list = data.get("source_list")
    if isinstance(source_list, list):
        data["source_list"] = [
            source for source in source_list if _source_has_locator(source)
        ]
    return data


def _normalize_market_state_card(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    card = dict(value)
    for key in ("price", "change_pct"):
        card[key] = _normalize_optional_float(card.get(key))
    card["as_of"] = _normalize_optional_text(card.get("as_of"))
    return card


def _normalize_judgment(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    judgment = dict(value)
    claim_type = judgment.get("claim_type")
    if isinstance(claim_type, str):
        normalized = " ".join(claim_type.replace("_", " ").split()).casefold()
        mapping = {
            "direct": "direct_evidence",
            "direct evidence": "direct_evidence",
            "cross evidence": "cross_evidence_inference",
            "cross evidence inference": "cross_evidence_inference",
            "cross-evidence inference": "cross_evidence_inference",
            "inference": "cross_evidence_inference",
            "inferred": "cross_evidence_inference",
            "interpretation": "interpretive",
            "interpretive judgment": "interpretive",
            "watch": "watchlist",
            "watch list": "watchlist",
        }
        judgment["claim_type"] = mapping.get(normalized, "interpretive")
    return judgment


def _source_has_locator(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return True
    url = value.get("url")
    rag_doc_id = value.get("rag_doc_id")
    title = value.get("title")
    return bool(
        (isinstance(url, str) and url.strip())
        or (isinstance(rag_doc_id, str) and rag_doc_id.strip())
        or (isinstance(title, str) and title.strip())
    )


def _normalize_optional_float(value: Any) -> Any:
    if value is None or isinstance(value, int | float):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text or text.casefold() in {"n/a", "na", "none", "null", "unavailable"}:
            return None
        try:
            return float(text.rstrip("%"))
        except ValueError:
            return value
    return value


def _normalize_optional_text(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.casefold() in {"n/a", "na", "none", "null", "unavailable"}:
            return None
        return text
    return value


def _split_validation_errors(exc: ValidationError) -> tuple[list[str], list[str], list[str]]:
    missing: list[str] = []
    errors: list[str] = []
    findings: list[str] = []

    for err in exc.errors():
        decoded = decode_findings(str(err.get("msg", "")))
        if decoded is not None:
            findings.extend(decoded)
            continue

        loc = _format_loc(err.get("loc", ()))
        err_type = str(err.get("type", "validation_error"))
        if err_type == "missing":
            missing.append(loc)
        else:
            errors.append(f"{loc}:{err_type}:{err.get('msg', '')}")

    return missing, errors, findings


def _format_loc(loc: object) -> str:
    if not isinstance(loc, tuple):
        return str(loc) if loc else "__root__"
    if not loc:
        return "__root__"

    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
        else:
            parts.append(str(item))
    return ".".join(parts)


__all__ = [
    "MacroBriefValidationError",
    "parse_macro_brief",
]
