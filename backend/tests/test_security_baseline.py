"""Checks for the secret-handling baseline that applies from Milestone 1 (SECURITY §1)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
SECRET_NAME_PARTS = ("KEY", "SECRET", "PASSWORD", "TOKEN", "URL")
SAFE_PLACEHOLDERS = ("", "replace-me")


def test_health_works_without_database_or_llm_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("DATABASE_URL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    client = TestClient(create_app(Settings()))

    assert client.get("/health").status_code == 200


def test_settings_do_not_read_env_files() -> None:
    # SECURITY §1: values come from the process environment only.
    assert Settings.model_config.get("env_file") is None


def test_env_example_holds_only_safe_placeholders() -> None:
    checked = 0
    for raw_line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        if not any(part in name.upper() for part in SECRET_NAME_PARTS):
            continue
        checked += 1
        is_angle_placeholder = value.startswith("<") and value.endswith(">")
        assert value in SAFE_PLACEHOLDERS or is_angle_placeholder, (
            f"{name} in .env.example must be empty or an obvious placeholder"
        )

    assert checked > 0, "expected at least one secret-like variable to check"
