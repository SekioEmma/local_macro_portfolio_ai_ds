from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import ofr_fsi_provider  # noqa: E402


def discover(*, live: bool) -> dict:
    if not live:
        return {
            "status": "not_run",
            "reason": "live_disabled",
            "download_url": ofr_fsi_provider.OFR_FSI_FALLBACK_URL,
            "discovery_method": "configured_fallback",
        }
    result = ofr_fsi_provider.fetch_text(ofr_fsi_provider.OFR_FSI_PAGE_URL)
    if result.get("status") != "ok":
        return {
            "status": "fallback",
            "reason": result.get("error"),
            "download_url": ofr_fsi_provider.OFR_FSI_FALLBACK_URL,
            "discovery_method": "configured_fallback",
        }
    discovered = ofr_fsi_provider.discover_download_url(result["text"])
    return {
        "status": "ok",
        "download_url": discovered or ofr_fsi_provider.OFR_FSI_FALLBACK_URL,
        "discovery_method": (
            "official_page_form_action" if discovered else "configured_fallback"
        ),
        "retrieved_at": result.get("retrieved_at"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover the official OFR FSI CSV download URL."
    )
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(discover(live=args.live), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
