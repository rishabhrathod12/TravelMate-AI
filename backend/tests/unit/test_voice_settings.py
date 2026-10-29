"""Voice settings: off by default, explicit limits when on, never in production (Step B)."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings

GOOD: dict[str, Any] = {
    "voice_enabled": True,
    "voice_dev_principal": "dev-1",
    "voice_session_max_seconds": 600,
    "voice_session_idle_seconds": 120,
    "voice_max_active_sessions_per_owner": 1,
    "voice_max_sessions_per_day_per_owner": 20,
}


def make(**overrides: Any) -> Settings:
    return Settings.model_validate({**GOOD, **overrides})


def test_voice_is_off_by_default_and_needs_nothing() -> None:
    settings = Settings()

    assert settings.voice_enabled is False
    assert settings.voice_dev_principal is None
    assert settings.voice_session_max_seconds is None


def test_complete_settings_are_accepted() -> None:
    settings = make()

    assert settings.voice_enabled is True
    assert settings.voice_session_idle_seconds == 120


@pytest.mark.parametrize(
    "missing",
    [
        "voice_dev_principal",
        "voice_session_max_seconds",
        "voice_session_idle_seconds",
        "voice_max_active_sessions_per_owner",
        "voice_max_sessions_per_day_per_owner",
    ],
)
def test_turning_voice_on_requires_every_setting(missing: str) -> None:
    with pytest.raises(ValidationError):
        make(**{missing: None})


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_principal_is_refused(blank: str) -> None:
    with pytest.raises(ValidationError, match="VOICE_DEV_PRINCIPAL"):
        make(voice_dev_principal=blank)


@pytest.mark.parametrize(
    "field",
    [
        "voice_session_max_seconds",
        "voice_session_idle_seconds",
        "voice_max_active_sessions_per_owner",
        "voice_max_sessions_per_day_per_owner",
    ],
)
@pytest.mark.parametrize("bad", [0, -1])
def test_limits_must_be_positive(field: str, bad: int) -> None:
    overrides: dict[str, Any] = {field: bad}
    if field == "voice_session_idle_seconds":
        overrides["voice_session_max_seconds"] = 600

    with pytest.raises(ValidationError):
        make(**overrides)


def test_the_idle_limit_cannot_exceed_the_session_limit() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        make(voice_session_max_seconds=60, voice_session_idle_seconds=120)


def test_voice_refuses_to_start_in_production() -> None:
    with pytest.raises(ValidationError, match="production"):
        make(app_env="production")


def test_voice_settings_are_not_checked_while_voice_is_off() -> None:
    settings = Settings.model_validate({"voice_enabled": False, "app_env": "production"})

    assert settings.voice_enabled is False


def test_blank_environment_values_count_as_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "VOICE_DEV_PRINCIPAL",
        "VOICE_SESSION_MAX_SECONDS",
        "VOICE_SESSION_IDLE_SECONDS",
        "VOICE_MAX_ACTIVE_SESSIONS_PER_OWNER",
        "VOICE_MAX_SESSIONS_PER_DAY_PER_OWNER",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("VOICE_ENABLED", "false")

    settings = Settings()

    assert settings.voice_session_max_seconds is None
    assert settings.voice_enabled is False


def test_the_voice_flag_can_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setenv("VOICE_DEV_PRINCIPAL", "dev-1")
    monkeypatch.setenv("VOICE_SESSION_MAX_SECONDS", "300")
    monkeypatch.setenv("VOICE_SESSION_IDLE_SECONDS", "60")
    monkeypatch.setenv("VOICE_MAX_ACTIVE_SESSIONS_PER_OWNER", "2")
    monkeypatch.setenv("VOICE_MAX_SESSIONS_PER_DAY_PER_OWNER", "10")

    settings = Settings()

    assert settings.voice_enabled is True
    assert settings.voice_session_max_seconds == 300
