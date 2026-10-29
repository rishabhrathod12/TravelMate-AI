"""Errors raised by domain rules."""


class DomainError(Exception):
    """Base class for domain rule violations."""


class CurrencyMismatchError(DomainError):
    """Raised when money in different currencies is added or compared."""
