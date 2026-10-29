"""Typed application settings loaded from environment variables.

Settings are read only from the process environment (SECURITY §1). This module
does not read `.env` files; local values are supplied by the shell or the
process manager.
"""

from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend.

    No secrets are defined yet. The health endpoint needs none.
    """

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    booking_enabled: bool = False

    # Where each data category comes from (SECURITY §1). "live" is a valid value for
    # the future, but no live provider exists (Milestone 13), so the application
    # refuses to start with it (app.providers.factory).
    provider_mode_transport: Literal["mock", "live"] = "mock"
    provider_mode_hotel: Literal["mock", "live"] = "mock"
    provider_mode_weather: Literal["mock", "live"] = "mock"

    # Language model (SECURITY §1). Optional: the local demo and every test run without
    # them. The key is a SecretStr, so printing the settings never shows it, and it is
    # read only from the environment. A blank value counts as not set.
    openai_api_key: SecretStr | None = None
    llm_model: str | None = None

    # Voice sessions (docs/VOICE_ASSISTANT_PLAN.md, ADR 0002). Off by default. When on, every
    # limit below must be set explicitly: there are no hidden defaults for how long a session
    # may last or how many a person may open. No vendor and no key exist yet, so a session
    # carries no audio.
    voice_enabled: bool = False
    # The one person the API acts for in local development (SECURITY §2). Real
    # authentication is PRD Q4 and does not exist, so voice refuses to start in production.
    voice_dev_principal: str | None = None
    voice_session_max_seconds: int | None = None
    voice_session_idle_seconds: int | None = None
    voice_max_active_sessions_per_owner: int | None = None
    voice_max_sessions_per_day_per_owner: int | None = None

    @field_validator(
        "voice_dev_principal",
        "voice_session_max_seconds",
        "voice_session_idle_seconds",
        "voice_max_active_sessions_per_owner",
        "voice_max_sessions_per_day_per_owner",
        mode="before",
    )
    @classmethod
    def _blank_voice_values_count_as_not_set(cls, value: object) -> object:
        # `.env.example` lists these names with empty values. Only the voice settings treat a
        # blank as unset; the other settings keep their stricter behaviour.
        return None if isinstance(value, str) and value.strip() == "" else value

    @model_validator(mode="after")
    def _voice_needs_explicit_limits_and_a_non_production_environment(self) -> "Settings":
        if not self.voice_enabled:
            return self
        if self.app_env == "production":
            raise ValueError(
                "VOICE_ENABLED cannot be true in production: voice sessions need real "
                "authentication (PRD Q4), which does not exist yet"
            )
        if self.voice_dev_principal is None or not self.voice_dev_principal.strip():
            raise ValueError("VOICE_DEV_PRINCIPAL must be set when VOICE_ENABLED is true")
        limits = {
            "VOICE_SESSION_MAX_SECONDS": self.voice_session_max_seconds,
            "VOICE_SESSION_IDLE_SECONDS": self.voice_session_idle_seconds,
            "VOICE_MAX_ACTIVE_SESSIONS_PER_OWNER": self.voice_max_active_sessions_per_owner,
            "VOICE_MAX_SESSIONS_PER_DAY_PER_OWNER": self.voice_max_sessions_per_day_per_owner,
        }
        for name, value in limits.items():
            if value is None or value < 1:
                raise ValueError(f"{name} must be set to a positive whole number when voice is on")
        if (self.voice_session_idle_seconds or 0) > (self.voice_session_max_seconds or 0):
            raise ValueError("VOICE_SESSION_IDLE_SECONDS cannot exceed VOICE_SESSION_MAX_SECONDS")
        return self

    @model_validator(mode="after")
    def _booking_must_stay_disabled(self) -> "Settings":
        # Booking execution is not implemented before Milestone 14 (ARCHITECTURE §6,
        # SECURITY §4). Refusing to start here stops an accidental enablement.
        if self.booking_enabled:
            raise ValueError("BOOKING_ENABLED must be false: booking execution is not implemented")
        return self
