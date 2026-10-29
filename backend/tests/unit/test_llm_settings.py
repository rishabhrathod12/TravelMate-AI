"""The key and model settings (SECURITY §1): environment only, never printed."""

from pathlib import Path

import pytest

from app.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"
FAKE_KEY = "sk-test-NOT-A-REAL-KEY-98765"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_neither_the_key_nor_the_model_is_required() -> None:
    settings = Settings()

    assert settings.openai_api_key is None
    assert settings.llm_model is None


def test_both_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("llm_model", "some-model")

    settings = Settings()

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == FAKE_KEY
    assert settings.llm_model == "some-model"


def test_the_key_never_appears_when_the_settings_are_printed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    settings = Settings()

    for text in (
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        str(settings.model_dump()),
    ):
        assert FAKE_KEY not in text
        assert "NOT-A-REAL-KEY" not in text


def test_a_blank_key_is_kept_as_blank_for_the_client_to_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")

    settings = Settings()

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == ""


def test_the_example_environment_file_lists_the_names_with_empty_values() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    assert "OPENAI_API_KEY=" in lines
    assert "LLM_MODEL=" in lines


def test_no_real_looking_key_is_in_the_example_file() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "sk-" not in text


def test_booking_is_still_refused() -> None:
    with pytest.raises(ValueError, match="BOOKING_ENABLED must be false"):
        Settings(booking_enabled=True)
