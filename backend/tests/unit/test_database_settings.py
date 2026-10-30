"""DATABASE_URL: a secret, PostgreSQL only, required in production (SECURITY §1; plan M9)."""

import pytest
from pydantic import ValidationError

from app.config import Settings

URL = "postgresql+psycopg://travelmate_login:s3cr3t-pass@127.0.0.1:5432/travelmate"


def test_the_database_is_optional_in_development() -> None:
    assert Settings().database_url is None


def test_a_database_url_is_accepted_and_kept_secret() -> None:
    settings = Settings.model_validate({"database_url": URL})

    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == URL
    assert "s3cr3t-pass" not in repr(settings) and "s3cr3t-pass" not in str(settings)


@pytest.mark.parametrize("url", ["postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"])
def test_postgresql_urls_are_accepted(url: str) -> None:
    assert Settings.model_validate({"database_url": url}).database_url is not None


@pytest.mark.parametrize(
    "url", ["sqlite:///x.db", "mysql://u:p@h/db", "file.db", "http://example.com"]
)
def test_anything_that_is_not_postgresql_is_refused(url: str) -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings.model_validate({"database_url": url})


def test_a_blank_url_counts_as_not_set() -> None:
    assert Settings.model_validate({"database_url": "  "}).database_url is None


def test_production_refuses_to_start_without_a_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings.model_validate({"app_env": "production"})
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings.model_validate({"app_env": "production", "database_url": " "})


def test_production_starts_with_a_database_url() -> None:
    settings = Settings.model_validate({"app_env": "production", "database_url": URL})

    assert settings.app_env == "production"


def test_the_error_does_not_print_a_url_that_was_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings.model_validate({"database_url": "mysql://u:hunter2@h/db"})

    assert "hunter2" not in str(caught.value)


def test_no_setting_error_ever_prints_the_rejected_input() -> None:
    bad = {"openai_api_key": "sk-FAKE-leak-check-123456", "llm_live_enabled": True}

    with pytest.raises(ValidationError) as caught:
        Settings.model_validate(bad)

    assert "sk-FAKE-leak-check-123456" not in str(caught.value)
    assert "input_value" not in str(caught.value)
