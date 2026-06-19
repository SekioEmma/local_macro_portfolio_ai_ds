from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_context.gdelt_registry import audit_gdelt_registry  # noqa: E402


CORE_PATHS = (
    SRC_ROOT / "data_quality",
    SRC_ROOT / "modeling",
    SRC_ROOT / "portfolio",
)


def audit_core_import_boundaries() -> list[str]:
    errors = []
    for root in CORE_PATHS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            imports_research_context = any(
                line.strip().startswith(("import ", "from "))
                and ("research_context" in line or "gdelt" in line.lower())
                for line in text.splitlines()
            )
            if imports_research_context:
                errors.append(f"core_model_imports_research_context:{path.relative_to(PROJECT_ROOT)}")
    return errors


def main() -> int:
    errors = audit_gdelt_registry() + audit_core_import_boundaries()
    print(
        json.dumps(
            {"status": "ok" if not errors else "error", "errors": errors},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
