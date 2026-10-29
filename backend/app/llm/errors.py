"""Typed LLM errors (ARCHITECTURE §9).

ARCHITECTURE §9: "Timeouts and rate limits retry once. Invalid structured output
triggers one repair attempt, then the step fails with a clear error." So only a
timeout and a rate limit are marked retryable.

Messages never contain the API key, a prompt, or text the model produced.
"""


class LLMError(Exception):
    """Base class for a failure while using the language model."""

    retryable: bool = False


class LLMTimeout(LLMError):
    retryable = True


class LLMRateLimited(LLMError):
    retryable = True


class LLMUnavailable(LLMError):
    """The service answered with a server error or could not be reached."""


class LLMConfigurationError(LLMError):
    """Something needed to call the model is missing or was refused (for example the key)."""


class LLMOutputError(LLMError):
    """The model's answer could not be used. `problems` say what was wrong, never the content."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("the model's answer was not usable: " + "; ".join(problems))
        self.problems = problems


class ItineraryRejected(LLMError):
    """The drafted itinerary was still unusable after the one allowed repair attempt."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("the itinerary was rejected: " + "; ".join(problems))
        self.problems = problems
