import pytest

from app.providers.errors import (
    ProviderConfigurationError,
    ProviderError,
    ProviderInvalidResponse,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

RETRYABLE = [ProviderUnavailable, ProviderRateLimited, ProviderTimeout]


@pytest.mark.parametrize(
    "error_class", [*RETRYABLE, ProviderInvalidResponse], ids=lambda cls: cls.__name__
)
def test_each_failure_kind_is_a_provider_error(error_class: type[ProviderError]) -> None:
    assert issubclass(error_class, ProviderError)


@pytest.mark.parametrize("error_class", RETRYABLE, ids=lambda cls: cls.__name__)
def test_timeouts_rate_limits_and_server_failures_may_be_retried(
    error_class: type[ProviderError],
) -> None:
    assert error_class.retryable is True


def test_an_invalid_response_is_never_retried() -> None:
    assert ProviderInvalidResponse.retryable is False


def test_an_unclassified_provider_error_is_not_retried() -> None:
    # Retrying must be an explicit decision for each kind of failure.
    assert ProviderError.retryable is False


def test_the_four_kinds_are_distinct_classes() -> None:
    kinds = {ProviderUnavailable, ProviderRateLimited, ProviderTimeout, ProviderInvalidResponse}

    assert len(kinds) == 4


def test_the_error_names_its_provider() -> None:
    error = ProviderTimeout("mock-transport", "no answer in 5 seconds")

    assert error.provider_name == "mock-transport"
    assert str(error) == "mock-transport: no answer in 5 seconds"


def test_a_configuration_error_is_not_a_provider_error() -> None:
    # So the retry helper can never retry a startup problem.
    assert not issubclass(ProviderConfigurationError, ProviderError)
