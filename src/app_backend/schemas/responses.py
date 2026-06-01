from __future__ import annotations

from pydantic import BaseModel


class StatusResponse(BaseModel):
    app_name: str
    mode: str
    storage_mode: str
    api_keys_configured: dict[str, bool]
    privacy_boundaries: list[str]
    project_root_exists: bool
