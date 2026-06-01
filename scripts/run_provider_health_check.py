from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import (  # noqa: E402
    alpha_vantage_provider,
    bea_provider,
    bls_provider,
    fedfunds_provider,
    fred_provider,
    treasury_provider,
    yfinance_provider,
)


SAVE_PATH = PROJECT_ROOT / "outputs" / "reports" / "provider_health_check.json"
API_KEY_ENV = {
    "fred_dgs10": "FRED_API_KEY",
    "alpha_vantage_gold": "ALPHA_VANTAGE_API_KEY",
    "bea_pce": "BEA_API_KEY",
}
PUBLIC_CHECK_KEYS = {
    "yfinance_sp500",
    "treasury_10y",
    "bls_cpi",
    "ny_fed_effr",
}


def main() -> int:
    args = _parse_args()
    _load_dotenv_if_available()
    generated_at = _utc_now()
    checks = run_health_checks(timeout_seconds=args.timeout_seconds)
    summary = summarize_checks(checks)
    result = {
        "generated_at": generated_at,
        "overall_status": overall_status(checks),
        "summary": summary,
        "checks": checks,
    }

    if args.save:
        SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SAVE_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def run_health_checks(timeout_seconds: int = 20) -> list[dict[str, Any]]:
    del timeout_seconds  # Provider wrappers own their request timeouts.
    check_specs: list[tuple[str, str, Callable[[], dict[str, Any]]]] = [
        ("fred_dgs10", "FRED", lambda: fred_provider.get_fred_latest("DGS10")),
        ("yfinance_sp500", "yfinance", lambda: yfinance_provider.get_latest_price("^GSPC")),
        ("alpha_vantage_gold", "Alpha Vantage", alpha_vantage_provider.get_gold_spot),
        ("treasury_10y", "U.S. Treasury", lambda: treasury_provider.get_par_yield("10y")),
        (
            "bls_cpi",
            "BLS",
            lambda: bls_provider.get_latest_observation(
                "CUSR0000SA0",
                primary_source="FRED:CPIAUCSL",
            ),
        ),
        ("bea_pce", "BEA", lambda: bea_provider.get_latest_pce_price_index("headline_pce")),
        ("ny_fed_effr", "New York Fed", fedfunds_provider.get_latest_effr),
    ]

    checks = []
    for key, provider, callback in check_specs:
        missing_key = _missing_key_check(key, provider)
        if missing_key is not None:
            checks.append(missing_key)
            continue

        try:
            checks.append(_result_to_check(key, provider, callback()))
        except Exception as exc:
            checks.append(
                {
                    "key": key,
                    "provider": provider,
                    "status": "error",
                    "source": provider,
                    "observation_date": None,
                    "value_present": False,
                    "error_type": exc.__class__.__name__,
                    "error_summary": _safe_error_summary(str(exc)),
                }
            )
    return checks


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"ok": 0, "skipped": 0, "error": 0}
    for check in checks:
        status = str(check.get("status") or "error")
        summary[status] = summary.get(status, 0) + 1
    return summary


def overall_status(checks: list[dict[str, Any]]) -> str:
    public_checks = [check for check in checks if check.get("key") in PUBLIC_CHECK_KEYS]
    public_errors = [check for check in public_checks if check.get("status") == "error"]
    if public_checks and len(public_errors) == len(public_checks):
        return "error"
    if public_errors:
        return "degraded"
    return "ok"


def _missing_key_check(key: str, provider: str) -> dict[str, Any] | None:
    env_name = API_KEY_ENV.get(key)
    if env_name is None or os.getenv(env_name):
        return None
    return {
        "key": key,
        "provider": provider,
        "status": "skipped",
        "source": provider,
        "observation_date": None,
        "value_present": False,
        "error_type": "missing_key",
        "error_summary": f"{env_name} not configured",
    }


def _result_to_check(key: str, provider: str, result: dict[str, Any]) -> dict[str, Any]:
    status = "ok" if result.get("status") == "ok" else "error"
    error_summary = _safe_error_summary(result.get("error"))
    return {
        "key": key,
        "provider": provider,
        "status": status,
        "source": result.get("source") or provider,
        "observation_date": _observation_date(result),
        "value_present": result.get("value") is not None,
        "error_type": None if status == "ok" else _error_type(error_summary),
        "error_summary": None if status == "ok" else error_summary,
    }


def _observation_date(result: dict[str, Any]) -> str | None:
    value = result.get("observation_date") or result.get("timestamp")
    if value is None:
        return None
    return str(value)[:10]


def _error_type(error_summary: str | None) -> str:
    text = str(error_summary or "").lower()
    if "api_key" in text and "not configured" in text:
        return "missing_key"
    if "import failed" in text:
        return "import_error"
    if "http status" in text:
        return "http_error"
    if "too many requests" in text or "rate limited" in text:
        return "rate_limited"
    if "request failed" in text:
        return "request_error"
    if "not json" in text or "parse" in text:
        return "parse_error"
    if "no valid" in text or "missing" in text or "empty" in text:
        return "empty_response"
    return "provider_error"


def _safe_error_summary(value: Any, max_length: int = 200) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    for env_name in ("FRED_API_KEY", "ALPHA_VANTAGE_API_KEY", "BEA_API_KEY", "BLS_API_KEY"):
        secret = os.getenv(env_name)
        if secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[redacted]", text)
    text = re.sub(
        r"(?i)(api[_-]?key|apikey|userid)=([^&\s]+)",
        r"\1=[redacted]",
        text,
    )
    if len(text) > max_length:
        return text[: max_length - 3].rstrip() + "..."
    return text


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run compact provider smoke checks without printing raw responses.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save compact summary to outputs/reports/provider_health_check.json.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=20,
        help="Reserved smoke-test timeout budget; provider wrappers keep compact request timeouts.",
    )
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
