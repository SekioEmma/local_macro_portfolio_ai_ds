from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import alpha_vantage_history_provider, market_history_store  # noqa: E402
from data_providers.source_registry import source_audit_metadata  # noqa: E402


PROXY_SYMBOLS: dict[str, dict[str, str]] = {
    "SPY": {"metric_key": "proxy_spy_close", "role": "cap_weight_equity_proxy"},
    "QQQ": {"metric_key": "proxy_qqq_close", "role": "growth_equity_proxy"},
    "RSP": {"metric_key": "proxy_rsp_close", "role": "equal_weight_equity_proxy"},
    "TLT": {"metric_key": "proxy_tlt_close", "role": "long_duration_treasury_proxy"},
    "GLD": {"metric_key": "proxy_gld_close", "role": "gold_etf_proxy"},
    "HYG": {"metric_key": "proxy_hyg_close", "role": "high_yield_etf_proxy"},
    "LQD": {"metric_key": "proxy_lqd_close", "role": "investment_grade_etf_proxy"},
    "SHY": {"metric_key": "proxy_shy_close", "role": "short_treasury_etf_proxy"},
}


def normalize_proxy_history(
    payload: dict[str, Any], *, symbol: str
) -> list[dict[str, Any]]:
    if symbol not in PROXY_SYMBOLS:
        raise ValueError(f"unsupported_proxy_symbol:{symbol}")
    if payload.get("status") != "ok":
        return []
    if str(payload.get("symbol") or symbol).upper() != symbol:
        raise ValueError("alpha_vantage_symbol_mismatch")
    fetched_at = str(payload.get("timestamp") or "")
    config = PROXY_SYMBOLS[symbol]
    observations = []
    for item in payload.get("observations", []):
        observation_date = str(item.get("date") or "").strip()
        close = _to_float_or_none(item.get("close"))
        if not observation_date or close is None:
            continue
        audit = source_audit_metadata(
            "alpha_vantage",
            source_series=symbol,
            retrieval_method="commercial_api",
            freshness_policy="market_daily",
            source_badge="commercial_api_fallback",
            ingested_at=fetched_at,
            extra={
                "proxy_role": config["role"],
                "source_priority": "below_official_and_dataset_sources",
            },
        )
        observations.append(
            {
                "metric_key": config["metric_key"],
                "observation_date": observation_date,
                "value": close,
                "value_text": str(close),
                "unit": "USD",
                "status": "ok",
                "source": "Alpha Vantage",
                "source_badge": "commercial_api_fallback",
                "provider": "alpha_vantage",
                "source_series": symbol,
                "generated_at": fetched_at,
                "fetched_at": fetched_at,
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": audit,
            }
        )
    return observations


def build_ingest_summary(
    *,
    symbols: list[str] | None = None,
    outputsize: str = "full",
    db_path: Path | str | None = None,
    dry_run: bool = True,
    live: bool = False,
    fetcher: Callable[[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selected = [symbol.upper() for symbol in (symbols or list(PROXY_SYMBOLS))]
    unknown = sorted(set(selected) - set(PROXY_SYMBOLS))
    if unknown:
        raise ValueError(f"unsupported_proxy_symbols:{','.join(unknown)}")
    summary: dict[str, Any] = {
        "symbols": selected,
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "errors": [],
        "rate_limit_stop": False,
        "dry_run": dry_run,
        "live": live,
    }
    if not live:
        summary["errors"].append("live_disabled")
        return summary
    active_fetcher = fetcher or alpha_vantage_history_provider.get_daily_time_series
    for symbol in selected:
        payload = active_fetcher(symbol, outputsize)
        if payload.get("status") != "ok":
            error = str(payload.get("error") or "fetch_failed")
            summary["errors"].append(f"{symbol}:{error}")
            if _is_rate_limit_error(error):
                summary["rate_limit_stop"] = True
                break
            continue
        observations = normalize_proxy_history(payload, symbol=symbol)
        summary["normalized_observations"] += len(observations)
        for observation in observations:
            if dry_run:
                continue
            result = market_history_store.upsert_market_observation(
                observation, db_path=db_path
            )
            summary[f"{result['status']}_count"] += 1
    return summary


def _is_rate_limit_error(error: str) -> bool:
    lowered = error.lower()
    return any(token in lowered for token in ("rate limit", "call frequency", "retry-after"))


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest Alpha Vantage ETF market proxies as support-only fallback data."
    )
    parser.add_argument("--symbols", nargs="+", choices=sorted(PROXY_SYMBOLS), default=None)
    parser.add_argument("--outputsize", choices=("compact", "full"), default="full")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        symbols=args.symbols,
        outputsize=args.outputsize,
        db_path=args.db_path,
        dry_run=args.dry_run or not args.write,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
