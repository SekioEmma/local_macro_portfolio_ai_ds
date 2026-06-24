from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_approved_official_history.py"
SPEC = importlib.util.spec_from_file_location("ingest_approved_official_history", SCRIPT)
assert SPEC and SPEC.loader
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class FakeService:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.calls = []
        self.raise_error = raise_error

    def run(self, route_key: str, **kwargs):
        self.calls.append((route_key, kwargs))
        if self.raise_error:
            raise RuntimeError("raw exception with secret")
        return {
            "route_key": route_key,
            "status": "planned" if not kwargs["live"] else "dry_run",
            "live": kwargs["live"],
            "write": kwargs["write"],
            "error_codes": ["live_disabled"] if not kwargs["live"] else [],
            "fred_limit": kwargs["fred_limit"],
            "start_year": kwargs["start_year"],
            "end_year": kwargs["end_year"],
        }


def _run(argv: list[str], service: FakeService):
    output = io.StringIO()
    code = cli.main(argv, service=service, output=output)
    return code, json.loads(output.getvalue())


def test_default_invocation_is_planned_and_not_live() -> None:
    service = FakeService()
    code, payload = _run(["--route", "fred_rates"], service)
    assert code == 0
    assert payload["status"] == "planned"
    assert payload["live"] is False
    assert payload["write"] is False
    assert service.calls == [
        (
            "fred_rates",
            {
                "live": False,
                "write": False,
                "fred_limit": 5000,
                "start_year": 2000,
                "end_year": None,
            },
        )
    ]


@pytest.mark.parametrize("argv", [["--route", "all"], ["--route", "unknown"]])
def test_route_validation_rejects_unknown_routes(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(argv, service=FakeService(), output=io.StringIO())


def test_write_without_live_is_rejected_before_service_call() -> None:
    service = FakeService()
    with pytest.raises(SystemExit):
        cli.main(["--route", "fred_rates", "--write"], service=service, output=io.StringIO())
    assert service.calls == []


def test_live_and_write_arguments_are_passed() -> None:
    service = FakeService()
    _, payload = _run(
        [
            "--route",
            "bls_cpi",
            "--live",
            "--write",
            "--fred-limit",
            "9",
            "--start-year",
            "2020",
            "--end-year",
            "2026",
        ],
        service,
    )
    assert payload["live"] is True
    assert payload["write"] is True
    assert service.calls[0][1] == {
        "live": True,
        "write": True,
        "fred_limit": 9,
        "start_year": 2020,
        "end_year": 2026,
    }


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_fred_limit_boundary(limit: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(
            ["--route", "fred_rates", "--fred-limit", limit],
            service=FakeService(),
            output=io.StringIO(),
        )


def test_bls_year_range_boundary() -> None:
    with pytest.raises(SystemExit):
        cli.main(
            ["--route", "bls_cpi", "--start-year", "2027", "--end-year", "2026"],
            service=FakeService(),
            output=io.StringIO(),
        )


def test_json_output_and_safe_exception_summary() -> None:
    output = io.StringIO()
    code = cli.main(["--route", "fred_rates"], service=FakeService(raise_error=True), output=output)
    payload = json.loads(output.getvalue())
    assert code == 0
    assert payload["status"] == "blocked"
    assert payload["error_codes"] == ["run_failed"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "raw exception" not in serialized
    assert "secret" not in serialized


def test_cli_source_has_no_unapproved_options_or_network_imports() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_tokens = [
        "--db-path",
        "--config",
        "--provider",
        "--series",
        "--url",
        "httpx",
        "requests",
        "aiohttp",
        "os.environ",
        "os.getenv",
    ]
    assert not any(token in source for token in forbidden_tokens)
