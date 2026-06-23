from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


DEFAULT_SEARCH_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "external_search.yaml"
)


class SearchAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    tavily_endpoint: str = "https://api.tavily.com/search"
    timeout_seconds: float = Field(default=30, gt=0)
    max_results_per_call: int = Field(default=5, ge=1)
    daily_call_budget: int = Field(default=0, ge=0)
    domain_allowlist: list[str] = Field(default_factory=list)
    domain_blocklist: list[str] = Field(default_factory=list)


def load_search_config(
    path: str | Path | None = None,
) -> SearchAdapterConfig:
    config_path = Path(path) if path is not None else DEFAULT_SEARCH_CONFIG_PATH
    if not config_path.is_file():
        return SearchAdapterConfig()

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError("Search config root must be a mapping.")
    return SearchAdapterConfig.model_validate(_normalize_mapping(loaded))


def _normalize_mapping(data: dict[Any, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in data.items()}


__all__ = [
    "DEFAULT_SEARCH_CONFIG_PATH",
    "SearchAdapterConfig",
    "load_search_config",
]
