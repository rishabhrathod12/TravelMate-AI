"""Bounded retries for idempotent provider reads (ARCHITECTURE §9, plan M3).

No test waits: `sleep` and `jitter` are replaced, and the number of calls is counted.
"""

from datetime import date

import pytest

from app.domain.options import TransportOption
from app.providers.base import ProviderMode, TransportProvider
from app.providers.errors import (
    ProviderError,
    ProviderInvalidResponse,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.mock.transport import MockTransportProvider
from app.providers.queries import TransportQuery
from app.providers.retry import SEARCH_POLICY, CallPolicy, retry_idempotent_read

RETRYABLE = [ProviderUnavailable, ProviderRateLimited, ProviderTimeout]
QUERY = TransportQuery.model_validate(
    {
        "origin": {"name": "Indore"},
        "destination": {"name": "Goa"},
        "departure_date": date(2026, 12, 1),
        "travellers": 1,
    }
)


class Recorder:
    """Stands in for `sleep`, and counts the calls an operation receives."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self.calls = 0

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class FlakyTransportProvider:
    """A fake provider that raises scripted errors, then answers like the mock."""

    name: str = "flaky-transport"
    mode: ProviderMode = ProviderMode.MOCK

    def __init__(self, failures: list[ProviderError]) -> None:
        self._failures = list(failures)
        self.calls = 0

    def search(self, query: TransportQuery) -> tuple[TransportOption, ...]:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return MockTransportProvider().search(query)


def run(
    provider: TransportProvider,
    recorder: Recorder,
    policy: CallPolicy = SEARCH_POLICY,
    jitter: float = 1.0,
) -> tuple[TransportOption, ...]:
    return retry_idempotent_read(
        lambda: provider.search(QUERY), policy, sleep=recorder.sleep, jitter=lambda: jitter
    )


class TestCallPolicy:
    def test_defaults_follow_the_architecture_document(self) -> None:
        # ARCHITECTURE §9: 5 second timeout for search, up to 2 retries.
        assert SEARCH_POLICY.timeout_seconds == 5.0
        assert SEARCH_POLICY.max_retries == 2

    @pytest.mark.parametrize(
        "bad", [{"timeout_seconds": 0}, {"max_retries": -1}, {"backoff_base_seconds": -0.1}]
    )
    def test_invalid_limits_are_rejected(self, bad: dict[str, float]) -> None:
        with pytest.raises(ValueError):
            CallPolicy(**bad)  # type: ignore[arg-type]

    def test_a_policy_cannot_be_changed_after_creation(self) -> None:
        with pytest.raises(AttributeError):
            SEARCH_POLICY.max_retries = 50  # type: ignore[misc]


class TestRetries:
    def test_a_first_attempt_that_works_is_not_retried(self) -> None:
        provider, recorder = FlakyTransportProvider([]), Recorder()

        options = run(provider, recorder)

        assert len(options) == 7
        assert provider.calls == 1
        assert recorder.sleeps == []

    @pytest.mark.parametrize("error_class", RETRYABLE, ids=lambda cls: cls.__name__)
    def test_a_retryable_failure_is_retried_until_it_works(
        self, error_class: type[ProviderError]
    ) -> None:
        provider = FlakyTransportProvider([error_class("flaky", "x"), error_class("flaky", "x")])
        recorder = Recorder()

        options = run(provider, recorder)

        assert len(options) == 7
        assert provider.calls == 3
        assert len(recorder.sleeps) == 2

    @pytest.mark.parametrize("error_class", RETRYABLE, ids=lambda cls: cls.__name__)
    def test_retries_are_bounded_and_the_typed_error_is_raised(
        self, error_class: type[ProviderError]
    ) -> None:
        failures = [error_class("flaky", f"attempt {n}") for n in range(10)]
        provider, recorder = FlakyTransportProvider(failures), Recorder()

        with pytest.raises(error_class) as raised:
            run(provider, recorder)

        # One first try and two retries: never more, however many failures are waiting.
        assert provider.calls == 3
        assert len(recorder.sleeps) == 2
        assert raised.value is failures[2]

    def test_an_invalid_response_is_not_retried(self) -> None:
        provider = FlakyTransportProvider([ProviderInvalidResponse("flaky", "bad shape")])
        recorder = Recorder()

        with pytest.raises(ProviderInvalidResponse):
            run(provider, recorder)

        assert provider.calls == 1
        assert recorder.sleeps == []

    def test_an_unexpected_exception_is_not_retried_or_hidden(self) -> None:
        recorder = Recorder()
        calls = 0

        def broken() -> None:
            nonlocal calls
            calls += 1
            raise ZeroDivisionError("bug")

        with pytest.raises(ZeroDivisionError):
            retry_idempotent_read(broken, sleep=recorder.sleep)

        assert calls == 1
        assert recorder.sleeps == []

    def test_the_last_error_wins_when_the_failures_differ(self) -> None:
        provider = FlakyTransportProvider(
            [
                ProviderTimeout("flaky", "first"),
                ProviderRateLimited("flaky", "second"),
                ProviderUnavailable("flaky", "third"),
            ]
        )

        with pytest.raises(ProviderUnavailable):
            run(provider, Recorder())

    @pytest.mark.parametrize(("retries", "expected_calls"), [(0, 1), (1, 2), (2, 3), (4, 5)])
    def test_the_number_of_calls_is_one_plus_the_allowed_retries(
        self, retries: int, expected_calls: int
    ) -> None:
        provider = FlakyTransportProvider([ProviderTimeout("flaky", "x") for _ in range(20)])

        with pytest.raises(ProviderTimeout):
            run(provider, Recorder(), policy=CallPolicy(max_retries=retries))

        assert provider.calls == expected_calls


class TestBackoff:
    def failing(self, count: int) -> FlakyTransportProvider:
        return FlakyTransportProvider([ProviderTimeout("flaky", "x") for _ in range(count)])

    def test_the_wait_doubles_with_each_retry(self) -> None:
        recorder = Recorder()

        run(self.failing(2), recorder, policy=CallPolicy(backoff_base_seconds=0.25), jitter=1.0)

        assert recorder.sleeps == [0.25, 0.5]

    def test_jitter_scales_the_wait_down(self) -> None:
        recorder = Recorder()

        run(self.failing(2), recorder, policy=CallPolicy(backoff_base_seconds=0.25), jitter=0.5)

        assert recorder.sleeps == [0.125, 0.25]

    def test_zero_jitter_means_no_wait(self) -> None:
        recorder = Recorder()

        run(self.failing(2), recorder, jitter=0.0)

        assert recorder.sleeps == [0.0, 0.0]

    @pytest.mark.parametrize("jitter", [0.0, 0.1, 0.5, 0.999])
    def test_no_wait_exceeds_the_exponential_ceiling(self, jitter: float) -> None:
        recorder = Recorder()
        policy = CallPolicy(max_retries=4, backoff_base_seconds=0.25)

        run(self.failing(4), recorder, policy=policy, jitter=jitter)

        for attempt, delay in enumerate(recorder.sleeps):
            assert 0 <= delay <= 0.25 * 2**attempt

    def test_there_is_no_wait_after_the_final_failure(self) -> None:
        recorder = Recorder()

        with pytest.raises(ProviderTimeout):
            run(self.failing(10), recorder)

        assert len(recorder.sleeps) == SEARCH_POLICY.max_retries
