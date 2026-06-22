from __future__ import annotations

from pathlib import Path

import pytest

from app_backend.services.search_config_loader import load_search_config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_complete_yaml_config(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "search.yaml",
        """
tavily_endpoint: https://example.test/search
timeout_seconds: 12
max_results_per_call: 7
daily_call_budget: 42
domain_allowlist:
  - reuters.com
domain_blocklist:
  - reddit.com
""",
    )

    config = load_search_config(config_path)

    assert config.tavily_endpoint == "https://example.test/search"
    assert config.timeout_seconds == 12
    assert config.max_results_per_call == 7
    assert config.daily_call_budget == 42
    assert config.domain_allowlist == ["reuters.com"]
    assert config.domain_blocklist == ["reddit.com"]


def test_missing_file_returns_safe_defaults(tmp_path: Path):
    config = load_search_config(tmp_path / "missing.yaml")

    assert config.timeout_seconds == 30
    assert config.max_results_per_call == 5
    assert config.daily_call_budget == 0
    assert config.domain_allowlist == []
    assert config.domain_blocklist == []


def test_missing_optional_fields_use_defaults(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "search.yaml",
        "tavily_endpoint: https://example.test/search\n",
    )

    config = load_search_config(config_path)

    assert config.timeout_seconds == 30
    assert config.max_results_per_call == 5
    assert config.daily_call_budget == 0
    assert config.domain_allowlist == []
    assert config.domain_blocklist == []


def test_negative_budget_raises_value_error(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "search.yaml",
        "daily_call_budget: -1\n",
    )

    with pytest.raises(ValueError):
        load_search_config(config_path)


def test_empty_domain_allowlist_is_preserved(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "search.yaml",
        "domain_allowlist: []\n",
    )

    config = load_search_config(config_path)

    assert config.domain_allowlist == []


def test_example_config_contains_no_real_tavily_key():
    example_path = (
        Path(__file__).resolve().parents[2]
        / "configs"
        / "external_search.yaml.example"
    )

    assert "tvly-" not in example_path.read_text(encoding="utf-8")
