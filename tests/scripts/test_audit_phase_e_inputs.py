from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_phase_e_inputs.py"
SPEC = importlib.util.spec_from_file_location("audit_phase_e_inputs", SCRIPT)
assert SPEC and SPEC.loader
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def test_build_phase_e_input_audit_loads_manual_oas_without_return_values(tmp_path: Path):
    oas_path = tmp_path / "oas_monthly.csv"
    _write_monthly_oas(oas_path, month_count=120)

    payload = cli.build_phase_e_input_audit(
        manual_oas_monthly=oas_path,
        generated_at="2026-06-27T00:00:00+00:00",
    )

    assert payload["status"] == "insufficient_inputs"
    assert payload["mode"] == "input_audit_only"
    assert payload["safety"]["network_access"] is False
    assert payload["safety"]["writes_database"] is False
    assert payload["safety"]["emits_raw_series_values"] is False
    assert payload["source_files"]["manual_oas_monthly"]["loaded"] is True
    assert payload["source_files"]["manual_oas_monthly"]["row_count"] == 120
    assert "credit_spread_hy" not in payload["phase_e_readiness"]["blocking_factors"]
    assert "real_yield_10y" in payload["phase_e_readiness"]["blocking_factors"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert '"values"' not in serialized.lower()
    assert "3.14" not in serialized


def test_missing_manual_oas_file_fails_soft():
    payload = cli.build_phase_e_input_audit(
        manual_oas_monthly=Path("missing.csv"),
        generated_at="2026-06-27T00:00:00+00:00",
    )

    assert payload["status"] == "insufficient_inputs"
    assert payload["source_files"]["manual_oas_monthly"]["exists"] is False
    assert "credit_spread_hy" in payload["phase_e_readiness"]["blocking_factors"]


def test_invalid_manual_oas_source_blocks_without_raw_exception(tmp_path: Path):
    oas_path = tmp_path / "oas_monthly.csv"
    _write_monthly_oas(oas_path, month_count=1, source_method="official")

    payload = cli.build_phase_e_input_audit(
        manual_oas_monthly=oas_path,
        generated_at="2026-06-27T00:00:00+00:00",
    )

    assert payload["status"] == "blocked"
    assert payload["error"] == {
        "code": "manual_oas_monthly_load_failed",
        "type": "ValueError",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "official" not in serialized


def test_cli_prints_json_and_can_save_copy(tmp_path: Path):
    oas_path = tmp_path / "oas_monthly.csv"
    save_path = tmp_path / "phase_e_audit.json"
    _write_monthly_oas(oas_path, month_count=84)
    output = io.StringIO()

    code = cli.main(
        [
            "--manual-oas-monthly",
            str(oas_path),
            "--real-yield-policy",
            "requires_decision",
            "--save-json",
            str(save_path),
        ],
        output=output,
    )

    assert code == 0
    stdout_payload = json.loads(output.getvalue())
    saved_payload = json.loads(save_path.read_text(encoding="utf-8"))
    assert stdout_payload["source_files"]["manual_oas_monthly"]["row_count"] == 84
    assert saved_payload["source_files"]["manual_oas_monthly"]["row_count"] == 84


def test_cli_source_has_no_network_or_database_imports():
    source = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden_tokens = [
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "sqlite3",
        "market_history_store",
        "os.environ",
        "os.getenv",
        "data/holdings",
        "outputs/",
    ]
    assert not any(token in source for token in forbidden_tokens)


def _write_monthly_oas(
    path: Path,
    *,
    month_count: int,
    source_method: str = cli.phase_e.MANUAL_AUDITED_DOWNLOAD,
) -> None:
    fieldnames = [
        "month",
        "observation_date",
        "oas_percent",
        "source_method",
        "source_series",
        "source_url",
        "captured_at",
    ]
    year = 2017
    month = 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(month_count):
            writer.writerow(
                {
                    "month": f"{year:04d}-{month:02d}",
                    "observation_date": f"{year:04d}-{month:02d}-28",
                    "oas_percent": "3.14",
                    "source_method": source_method,
                    "source_series": "BAMLH0A0HYM2",
                    "source_url": "https://sc.macromicro.me/series/78167",
                    "captured_at": "2026-06-26T13:32:39.599Z",
                }
            )
            month += 1
            if month == 13:
                year += 1
                month = 1
