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
    # The owner's separate switch for real model calls (ADR 0004, C3). Having a key set never
    # makes a call by itself: nothing reaches OpenAI unless this is true as well, and when it is
    # true the key, the model and an hourly cap on calls must all be set. Off by default.
    llm_live_enabled: bool = False
    llm_max_calls_per_hour: int | None = None
    # Writing a whole plan needs far more tokens and time than reading one message, so a live
    # plan has its own explicit limits. Not needed for the scripted sample.
    conversation_plan_max_output_tokens: int | None = None
    conversation_plan_timeout_seconds: float | None = None

    # The planning API (plan M8): trips, runs, selections, itinerary and cost estimate. Off by
    # default. Real authentication is PRD Q4 and does not exist, so every call acts for the one
    # configured development principal (SECURITY §2) and the API refuses to start in production.
    # Every limit has to be set: there are no hidden defaults for what a run may cost. The display
    # currency is PRD Q5 (open), so it is set explicitly too.
    api_enabled: bool = False
    api_dev_principal: str | None = None
    api_currency: str | None = None
    api_run_max_steps: int | None = None
    api_run_max_tool_calls: int | None = None
    api_run_max_human_rounds: int | None = None
    api_max_runs_per_hour_per_owner: int | None = None

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

    # Typed trip chat (docs/VOICE_ASSISTANT_PLAN.md, V5). Off by default. It uses a development
    # stand-in for the model (no real model is connected), so it refuses to start in production.
    # The limits are explicit for the same reason as the voice limits: no hidden defaults, and
    # PRD Q14 / Q19 (text and model limits) are still open.
    conversation_enabled: bool = False
    conversation_max_message_chars: int | None = None
    conversation_llm_max_output_tokens: int | None = None
    conversation_llm_timeout_seconds: float | None = None

    @field_validator(
        "api_dev_principal",
        "api_currency",
        "api_run_max_steps",
        "api_run_max_tool_calls",
        "api_run_max_human_rounds",
        "api_max_runs_per_hour_per_owner",
        "llm_max_calls_per_hour",
        "conversation_plan_max_output_tokens",
        "conversation_plan_timeout_seconds",
        "conversation_max_message_chars",
        "conversation_llm_max_output_tokens",
        "conversation_llm_timeout_seconds",
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
    def _conversation_needs_explicit_limits_and_a_non_production_environment(self) -> "Settings":
        if not self.conversation_enabled:
            return self
        if self.app_env == "production":
            raise ValueError(
                "CONVERSATION_ENABLED cannot be true in production: only a development "
                "stand-in for the language model exists"
            )
        limits = {
            "CONVERSATION_MAX_MESSAGE_CHARS": self.conversation_max_message_chars,
            "CONVERSATION_LLM_MAX_OUTPUT_TOKENS": self.conversation_llm_max_output_tokens,
            "CONVERSATION_LLM_TIMEOUT_SECONDS": self.conversation_llm_timeout_seconds,
        }
        for name, value in limits.items():
            if value is None or not value > 0:
                raise ValueError(f"{name} must be set to a positive number when chat is on")
        return self

    @model_validator(mode="after")
    def _live_model_calls_need_every_safeguard(self) -> "Settings":
        if not self.llm_live_enabled:
            return self
        if not (self.conversation_enabled or self.api_enabled):
            raise ValueError(
                "LLM_LIVE_ENABLED needs CONVERSATION_ENABLED or API_ENABLED: nothing else uses it"
            )
        key = self.openai_api_key.get_secret_value().strip() if self.openai_api_key else ""
        if not key:
            raise ValueError("OPENAI_API_KEY must be set when LLM_LIVE_ENABLED is true")
        if self.llm_model is None or not self.llm_model.strip():
            raise ValueError("LLM_MODEL must be set when LLM_LIVE_ENABLED is true")
        if self.llm_max_calls_per_hour is None or self.llm_max_calls_per_hour < 1:
            raise ValueError("LLM_MAX_CALLS_PER_HOUR must be a positive whole number when live")
        plan_limits = {
            "CONVERSATION_PLAN_MAX_OUTPUT_TOKENS": self.conversation_plan_max_output_tokens,
            "CONVERSATION_PLAN_TIMEOUT_SECONDS": self.conversation_plan_timeout_seconds,
        }
        for name, value in plan_limits.items():
            if value is None or not value > 0:
                raise ValueError(f"{name} must be set to a positive number when live")
        return self

    @model_validator(mode="after")
    def _api_needs_explicit_limits_and_a_non_production_environment(self) -> "Settings":
        if not self.api_enabled:
            return self
        if self.app_env == "production":
            raise ValueError(
                "API_ENABLED cannot be true in production: the planning API needs real "
                "authentication (PRD Q4), which does not exist yet"
            )
        if self.api_dev_principal is None or not self.api_dev_principal.strip():
            raise ValueError("API_DEV_PRINCIPAL must be set when API_ENABLED is true")
        if (
            self.api_currency is None
            or len(self.api_currency) != 3
            or not self.api_currency.isalpha()
        ):
            raise ValueError("API_CURRENCY must be a three-letter currency code when the API is on")
        limits = {
            "API_RUN_MAX_STEPS": self.api_run_max_steps,
            "API_RUN_MAX_TOOL_CALLS": self.api_run_max_tool_calls,
            "API_RUN_MAX_HUMAN_ROUNDS": self.api_run_max_human_rounds,
            "API_MAX_RUNS_PER_HOUR_PER_OWNER": self.api_max_runs_per_hour_per_owner,
        }
        for name, value in limits.items():
            if value is None or value < 1:
                raise ValueError(
                    f"{name} must be set to a positive whole number when the API is on"
                )
        return self

    @model_validator(mode="after")
    def _booking_must_stay_disabled(self) -> "Settings":
        # Booking execution is not implemented before Milestone 14 (ARCHITECTURE §6,
        # SECURITY §4). Refusing to start here stops an accidental enablement.
        if self.booking_enabled:
            raise ValueError("BOOKING_ENABLED must be false: booking execution is not implemented")
        return self
