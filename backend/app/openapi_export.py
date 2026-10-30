"""The OpenAPI document of the whole API, as a reviewed artifact (plan M8).

It is built from an app with every optional route switched on (voice, chat and planning) and
made-up settings, so it describes the full surface and holds no real value. A test compares the
committed file `docs/openapi.json` with a fresh build, so an API change that is not reviewed fails
the run. Regenerate it with `backend/scripts/export_openapi.py`.
"""

import json
from typing import Any

from app.config import Settings
from app.main import create_app

OPENAPI_RELATIVE_PATH = "docs/openapi.json"

_DOCUMENTED_SETTINGS: dict[str, Any] = {
    "voice_enabled": True,
    "voice_dev_principal": "docs",
    "voice_session_max_seconds": 600,
    "voice_session_idle_seconds": 120,
    "voice_max_active_sessions_per_owner": 2,
    "voice_max_sessions_per_day_per_owner": 5,
    "conversation_enabled": True,
    "conversation_max_message_chars": 300,
    "conversation_llm_max_output_tokens": 400,
    "conversation_llm_timeout_seconds": 5,
    "api_enabled": True,
    "api_dev_principal": "docs",
    "api_currency": "INR",
    "api_run_max_steps": 60,
    "api_run_max_tool_calls": 12,
    "api_run_max_human_rounds": 8,
    "api_max_runs_per_hour_per_owner": 5,
}


def build_openapi_document() -> str:
    app = create_app(Settings.model_validate(_DOCUMENTED_SETTINGS))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
