import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep tests independent of the developer's shell environment.
    for name in ("APP_ENV", "LOG_LEVEL", "BOOKING_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_safe() -> None:
    settings = Settings()

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.booking_enabled is False


def test_values_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"


def test_environment_names_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("app_env", "production")
    monkeypatch.setenv("database_url", "postgresql+psycopg://u:p@localhost/db")  # required there

    assert Settings().app_env == "production"


def test_unknown_app_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging-ish")

    with pytest.raises(ValidationError):
        Settings()


def test_booking_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Milestone 14 is the earliest point where this may change (ARCHITECTURE §6).
    monkeypatch.setenv("BOOKING_ENABLED", "true")

    with pytest.raises(ValidationError, match="BOOKING_ENABLED must be false"):
        Settings()
