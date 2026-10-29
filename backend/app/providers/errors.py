"""Typed provider errors (ARCHITECTURE §9, plan M3).

A provider either returns typed results or raises one of these. Tests assert on
the class, not on message text.

`retryable` marks the failures ARCHITECTURE §9 allows retrying for an idempotent
read: timeouts, rate limiting (429) and server-side failures (5xx). An invalid
response is never retried and never partly used.
"""


class ProviderError(Exception):
    """Base class for a failure while calling a provider."""

    retryable: bool = False

    def __init__(self, provider_name: str, message: str) -> None:
        super().__init__(f"{provider_name}: {message}")
        self.provider_name = provider_name


class ProviderUnavailable(ProviderError):
    """The provider could not be reached or answered with a server error (5xx)."""

    retryable = True


class ProviderRateLimited(ProviderError):
    """The provider refused the call because of rate limits (429)."""

    retryable = True


class ProviderTimeout(ProviderError):
    """The provider did not answer within the call's time limit."""

    retryable = True


class ProviderInvalidResponse(ProviderError):
    """The answer did not match the expected shape. It is rejected, never partly used."""

    retryable = False


class ProviderConfigurationError(Exception):
    """The provider settings ask for something that does not exist, so startup stops."""
