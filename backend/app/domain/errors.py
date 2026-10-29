"""Errors raised by domain rules."""


class DomainError(Exception):
    """Base class for domain rule violations."""


class CurrencyMismatchError(DomainError):
    """Raised when money in different currencies is added or compared."""


class InvalidTransitionError(DomainError):
    """Raised when a booking status change is not in the allowed transition table."""


class UnknownTimeZoneError(DomainError):
    """Raised when a time-zone name is not a known IANA zone."""
