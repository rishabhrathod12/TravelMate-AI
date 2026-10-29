"""Typed application settings loaded from environment variables.

Settings are read only from the process environment (SECURITY §1). This module
does not read `.env` files; local values are supplied by the shell or the
process manager.
"""

from typing import Literal

from pydantic import model_validator
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

    @model_validator(mode="after")
    def _booking_must_stay_disabled(self) -> "Settings":
        # Booking execution is not implemented before Milestone 14 (ARCHITECTURE §6,
        # SECURITY §4). Refusing to start here stops an accidental enablement.
        if self.booking_enabled:
            raise ValueError("BOOKING_ENABLED must be false: booking execution is not implemented")
        return self
