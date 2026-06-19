from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers.source_registry import (  # noqa: E402
    EXCLUDED_SOURCE_REGISTRY,
    PROVIDER_REGISTRY,
    audit_source_registry,
)


def main() -> int:
    errors = audit_source_registry()
    result = {
        "status": "ok" if not errors else "error",
        "provider_count": len(PROVIDER_REGISTRY),
        "excluded_source_count": len(EXCLUDED_SOURCE_REGISTRY),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
