from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "reports" / "bea_nipa_table_discovery.json"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import bea_history_provider  # noqa: E402


def discover_tables(*, live: bool) -> dict:
    if not live:
        return {"status": "not_run", "reason": "live_disabled", "tables": []}
    api_key = bea_history_provider.load_bea_api_key()
    if not api_key:
        return {"status": "not_available", "reason": "BEA_API_KEY not configured", "tables": []}
    result = bea_history_provider.request_bea(
        bea_history_provider.build_bea_discovery_params(api_key=api_key)
    )
    if result.get("status") != "ok":
        return {"status": "error", "reason": result.get("error"), "tables": []}
    tables = bea_history_provider.normalize_discovery(result["payload"])
    relevant = [
        item
        for item in tables
        if any(
            token in item["description"].lower()
            for token in ("gdp", "gross domestic product", "personal consumption", "price")
        )
    ]
    return {
        "status": "ok",
        "retrieved_at": result.get("retrieved_at"),
        "table_count": len(tables),
        "relevant_tables": relevant,
        "confirmed_production_mappings": bea_history_provider.BEA_NIPA_MAPPINGS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover BEA NIPA table metadata.")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-output", action="store_true")
    args = parser.parse_args(argv)
    result = discover_tables(live=args.live)
    if args.write_output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"ok", "not_run", "not_available"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
