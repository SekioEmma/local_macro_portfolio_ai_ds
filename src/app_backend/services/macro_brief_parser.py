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
    data = _load_json_object(payload)
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
