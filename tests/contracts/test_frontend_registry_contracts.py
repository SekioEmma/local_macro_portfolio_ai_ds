"""Frontend registry contract tests (semantic form).

These tests assert structural invariants between the backend ModelRegistry
and the frontend display registries, instead of pinning literal source
strings. The previous version asserted exact JSX / import / label strings,
which blocked any non-trivial refactor of the frontend. Keep these checks
implementation-agnostic so a frontend redesign can change file structure,
component names, and import paths without breaking the contract.

What is enforced:
- Every backend model_output module key has a label entry and an
  interpretation boundary entry in moduleRegistry.ts.
- Every model_output public output key has a label entry in
  metricRegistry.ts (so the UI never shows a raw key).
- displayLabels.ts exposes the expected helper functions and pulls from
  the registry files (no inline label tables).
- ModuleDetailDrawer reads boundary text from the registry helper rather
  than defining its own boundary table.
- No frontend source file contains raw provider / raw holdings payload
  identifiers (privacy guard).

What is NOT enforced anymore:
- Exact literal lines of TS source.
- Specific Chinese / English label text.
- File names of frontend components (registry helpers must exist by name
  but the components that consume them may move).
"""

from __future__ import annotations

import re
from pathlib import Path

from modeling.model_registry import ModelRegistry

_REPO_ROOT = Path(__file__).resolve().parents[2]


FRONTEND_SRC = _REPO_ROOT / "app_frontend/src"
MODULE_REGISTRY_PATH = FRONTEND_SRC / "utils/moduleRegistry.ts"
METRIC_REGISTRY_PATH = FRONTEND_SRC / "utils/metricRegistry.ts"
DISPLAY_LABELS_PATH = FRONTEND_SRC / "utils/displayLabels.ts"
MODULE_DRAWER_PATH = FRONTEND_SRC / "components/ModuleDetailDrawer.tsx"


_LABEL_ENTRY_RE = re.compile(
    r"""(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*["'][^"']+["']"""
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _keys_in_block(text: str, block_name: str) -> set[str]:
    """Return the set of object keys declared inside any object literal
    whose identifier matches `block_name`. Handles both
    `const X: Type = { ... };` and `Object.assign(X, { ... });` forms,
    accumulating across multiple declarations.
    """
    keys: set[str] = set()
    pattern_decl = re.compile(
        rf"\b{re.escape(block_name)}\b[^=]*=\s*\{{",
    )
    pattern_assign = re.compile(
        rf"Object\.assign\(\s*{re.escape(block_name)}\s*,\s*\{{",
    )
    for opener in list(pattern_decl.finditer(text)) + list(
        pattern_assign.finditer(text)
    ):
        start = opener.end() - 1
        depth = 0
        end = None
        for idx in range(start, len(text)):
            ch = text[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        if end is None:
            continue
        block = text[start + 1 : end]
        for match in _LABEL_ENTRY_RE.finditer(block):
            keys.add(match.group("key"))
    return keys


def test_module_registry_covers_every_backend_model_module():
    registry = ModelRegistry()
    text = _read(MODULE_REGISTRY_PATH)

    declared_labels = _keys_in_block(text, "moduleLabels")
    declared_boundaries = _keys_in_block(text, "interpretationBoundaries")
    expected = set(registry.model_output_module_keys())

    missing_labels = expected - declared_labels
    missing_boundaries = expected - declared_boundaries
    assert not missing_labels, (
        f"moduleRegistry.ts is missing labels for backend modules: "
        f"{sorted(missing_labels)}"
    )
    assert not missing_boundaries, (
        f"moduleRegistry.ts is missing interpretation boundaries for "
        f"backend modules: {sorted(missing_boundaries)}"
    )


def test_metric_registry_covers_every_public_output_key():
    registry = ModelRegistry()
    text = _read(METRIC_REGISTRY_PATH)
    declared_metric_labels = _keys_in_block(text, "metricLabels")

    missing: list[str] = []
    for module_key in sorted(registry.module_keys()):
        for output_key in registry.public_output_keys(module_key):
            if output_key not in declared_metric_labels:
                missing.append(f"{module_key}.{output_key}")
    assert not missing, (
        "metricRegistry.ts is missing labels for backend public output "
        f"keys: {missing[:10]}{' ...' if len(missing) > 10 else ''}"
    )


def test_display_labels_expose_required_helpers():
    text = _read(DISPLAY_LABELS_PATH)
    required_helpers = (
        "getModuleLabel",
        "getStatusLabel",
        "getSourceBadgeLabel",
        "getFreshnessLabel",
        "getAiContextLabel",
        "getMissingReasonLabel",
        "getMetricLabel",
    )
    missing = [
        name
        for name in required_helpers
        if not re.search(rf"\bexport\s+function\s+{name}\b", text)
    ]
    assert not missing, (
        f"displayLabels.ts must export helpers: {missing}"
    )


def test_display_labels_pull_from_registry_files():
    text = _read(DISPLAY_LABELS_PATH)
    required_imports = ("moduleLabels", "metricLabels", "statusLabels")
    missing = [name for name in required_imports if name not in text]
    assert not missing, (
        "displayLabels.ts must import label tables from registry files, "
        f"missing references: {missing}"
    )


def test_module_drawer_uses_registry_boundary_not_inline_table():
    text = _read(MODULE_DRAWER_PATH)
    assert "getModuleBoundary" in text, (
        "ModuleDetailDrawer.tsx must read boundary text from the registry "
        "helper getModuleBoundary, not from inline literals."
    )
    assert not re.search(r"const\s+interpretationBoundaries\s*[:=]", text), (
        "ModuleDetailDrawer.tsx must not declare its own "
        "interpretationBoundaries map; use moduleRegistry.ts as the source "
        "of truth."
    )


def test_interpretation_boundary_lookup_has_fallback():
    text = _read(MODULE_REGISTRY_PATH)
    assert re.search(
        r"interpretationBoundaries\s*\[\s*moduleKey\s*\]\s*\|\|",
        text,
    ), (
        "moduleRegistry.ts must expose a boundary lookup that falls back "
        "to a default when an unknown moduleKey is passed."
    )


def test_frontend_files_do_not_contain_raw_provider_or_holdings_payload_logic():
    forbidden = ("raw_provider", "raw_holdings")
    offenders: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")
    assert offenders == [], (
        "Frontend sources must never reference raw provider payloads or "
        f"raw holdings rows: {offenders}"
    )
