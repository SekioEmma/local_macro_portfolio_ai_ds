from __future__ import annotations

import os
from pathlib import Path

from app_backend.schemas.responses import StatusResponse


APP_NAME = "local_macro_portfolio_ai_ds"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
API_KEY_ENV_NAMES = {
    "deepseek": "DEEPSEEK_API_KEY",
    "fred": "FRED_API_KEY",
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
    "bea": "BEA_API_KEY",
    "tavily": "TAVILY_API_KEY",
}
PRIVACY_BOUNDARIES = [
    "api_keys_env_only",
    "holdings_not_returned",
    "data_private_not_served",
    "outputs_not_served_raw",
    "local_backend_only",
]


def build_status() -> StatusResponse:
    return StatusResponse(
        app_name=APP_NAME,
        mode="local_dev",
        storage_mode="file_based",
        api_keys_configured={
            provider: bool(os.getenv(env_name))
            for provider, env_name in API_KEY_ENV_NAMES.items()
        },
        privacy_boundaries=PRIVACY_BOUNDARIES,
        project_root_exists=PROJECT_ROOT.exists(),
    )
