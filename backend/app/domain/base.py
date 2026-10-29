"""Shared base class for domain models."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable base for domain models.

    Unknown fields are rejected so that stray or injected data fails loudly
    instead of being silently ignored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
