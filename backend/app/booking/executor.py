"""The booking executor interface and the one implementation that exists: disabled.

`BookingClient` is what a future provider adapter will implement (M14). It is declared here only so
the composition can be tested: a test hands a spying client to `build_booking_executor` and checks
that the disabled executor never touches it. Nothing implements it, and nothing in the application
creates one.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class BookingOutcome(StrEnum):
    # The only outcome that exists before M14. Confirmed, failed and needs-review arrive with the
    # executor that can produce them.
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class BookingAttempt:
    """What an executor would be asked to book. It names an approved quote by its hash."""

    intent_id: str
    approval_id: str
    quote_content_hash: str


class BookingClient(Protocol):
    """The provider-facing client of a future executor. No implementation exists."""

    def book(self, attempt: BookingAttempt) -> BookingOutcome: ...


class BookingExecutor(Protocol):
    def execute(self, attempt: BookingAttempt) -> BookingOutcome: ...


class BookingNotImplemented(RuntimeError):
    """Booking execution was asked for, and it does not exist yet."""


class DisabledBookingExecutor:
    """Refuses every attempt. It holds no client, so it cannot reach a provider by accident."""

    def execute(self, attempt: BookingAttempt) -> BookingOutcome:
        return BookingOutcome.DISABLED


def build_booking_executor(
    *, booking_enabled: bool, client: BookingClient | None = None
) -> BookingExecutor:
    """The executor for this configuration. Only the disabled one can be built.

    A client passed in is deliberately ignored: with booking off it must never be reachable, and
    with booking on there is nothing to build until M14.
    """
    if booking_enabled:
        raise BookingNotImplemented(
            "booking execution is not implemented (plan M14) and needs the owner's authorization"
        )
    return DisabledBookingExecutor()
