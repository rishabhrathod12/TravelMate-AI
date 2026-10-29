from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.booking_lifecycle import (
    ALLOWED_TRANSITIONS,
    EXECUTION_TRANSITIONS,
    MVP_TRANSITIONS,
    Approval,
    BookingIntent,
    BookingStatus,
    allowed_next,
    can_transition,
    require_transition,
)
from app.domain.errors import DomainError, InvalidTransitionError

S = BookingStatus

# Written out by hand, separately from the code under test.
EXPECTED_ALLOWED = {
    # Drawn in ARCHITECTURE §6.
    (S.DRAFT, S.QUOTED),
    (S.QUOTED, S.AWAITING_APPROVAL),
    (S.AWAITING_APPROVAL, S.APPROVED),
    (S.APPROVED, S.REVALIDATION),
    (S.REVALIDATION, S.BOOKING),
    (S.REVALIDATION, S.AWAITING_APPROVAL),
    (S.BOOKING, S.CONFIRMED),
    (S.BOOKING, S.FAILED),
    # Described in the ARCHITECTURE §6 rules and state table.
    (S.APPROVED, S.AWAITING_APPROVAL),
    (S.BOOKING, S.NEEDS_REVIEW),
    (S.QUOTED, S.EXPIRED),
    (S.AWAITING_APPROVAL, S.EXPIRED),
    # Cancelling before anything is sent.
    (S.DRAFT, S.CANCELLED),
    (S.QUOTED, S.CANCELLED),
    (S.AWAITING_APPROVAL, S.CANCELLED),
    (S.APPROVED, S.CANCELLED),
    (S.REVALIDATION, S.CANCELLED),
}

# Edges the documents leave open. They must stay rejected until the owner decides.
UNDECIDED_AND_REJECTED = [
    pytest.param(S.APPROVED, S.EXPIRED, id="expired-approval-to-EXPIRED"),
    pytest.param(S.REVALIDATION, S.EXPIRED, id="expired-during-revalidation"),
    pytest.param(S.DRAFT, S.EXPIRED, id="draft-has-no-valid_until"),
    pytest.param(S.BOOKING, S.CANCELLED, id="cancel-while-booking-in-flight"),
    pytest.param(S.BOOKING, S.EXPIRED, id="expire-while-booking-in-flight"),
    pytest.param(S.NEEDS_REVIEW, S.CANCELLED, id="cancel-unknown-outcome"),
    pytest.param(S.NEEDS_REVIEW, S.EXPIRED, id="expire-unknown-outcome"),
    pytest.param(S.NEEDS_REVIEW, S.CONFIRMED, id="resolve-needs-review"),
    pytest.param(S.NEEDS_REVIEW, S.FAILED, id="fail-needs-review"),
    pytest.param(S.FAILED, S.AWAITING_APPROVAL, id="retry-after-failure"),
    pytest.param(S.FAILED, S.BOOKING, id="rebook-after-failure"),
    pytest.param(S.FAILED, S.CANCELLED, id="cancel-after-failure"),
]


def test_there_are_exactly_the_eleven_documented_statuses() -> None:
    assert {s.name for s in BookingStatus} == {
        "DRAFT",
        "QUOTED",
        "AWAITING_APPROVAL",
        "APPROVED",
        "REVALIDATION",
        "BOOKING",
        "CONFIRMED",
        "FAILED",
        "NEEDS_REVIEW",
        "CANCELLED",
        "EXPIRED",
    }


def test_every_possible_pair_is_checked_against_the_table() -> None:
    pairs = list(product(BookingStatus, repeat=2))
    assert len(pairs) == 121

    for current, target in pairs:
        assert can_transition(current, target) is ((current, target) in EXPECTED_ALLOWED), (
            current,
            target,
        )


def test_the_table_has_exactly_the_expected_edges() -> None:
    assert ALLOWED_TRANSITIONS == EXPECTED_ALLOWED
    assert len(ALLOWED_TRANSITIONS) == 17


def test_mvp_and_execution_edges_do_not_overlap_and_make_up_the_table() -> None:
    assert MVP_TRANSITIONS.isdisjoint(EXECUTION_TRANSITIONS)
    assert MVP_TRANSITIONS | EXECUTION_TRANSITIONS == ALLOWED_TRANSITIONS


def test_mvp_edges_never_touch_the_execution_states() -> None:
    execution_states = {S.REVALIDATION, S.BOOKING, S.CONFIRMED, S.FAILED, S.NEEDS_REVIEW}

    for source, target in MVP_TRANSITIONS:
        assert source not in execution_states
        assert target not in execution_states


def test_the_mvp_can_reach_approved_but_not_a_booking() -> None:
    reachable = {S.DRAFT}
    frontier = [S.DRAFT]
    while frontier:
        current = frontier.pop()
        for source, target in MVP_TRANSITIONS:
            if source == current and target not in reachable:
                reachable.add(target)
                frontier.append(target)

    assert S.APPROVED in reachable
    assert reachable.isdisjoint({S.REVALIDATION, S.BOOKING, S.CONFIRMED})


@pytest.mark.parametrize(("current", "target"), UNDECIDED_AND_REJECTED)
def test_open_decisions_stay_rejected(current: BookingStatus, target: BookingStatus) -> None:
    assert can_transition(current, target) is False
    with pytest.raises(InvalidTransitionError):
        require_transition(current, target)


@pytest.mark.parametrize("status", list(BookingStatus))
def test_a_status_never_transitions_to_itself(status: BookingStatus) -> None:
    assert can_transition(status, status) is False


@pytest.mark.parametrize("status", [S.CONFIRMED, S.FAILED, S.NEEDS_REVIEW, S.CANCELLED, S.EXPIRED])
def test_final_and_blocked_states_have_no_exits(status: BookingStatus) -> None:
    assert allowed_next(status) == frozenset()


@pytest.mark.parametrize("status", list(BookingStatus))
def test_nothing_leads_back_to_draft(status: BookingStatus) -> None:
    assert can_transition(status, S.DRAFT) is False


@pytest.mark.parametrize("status", list(BookingStatus))
def test_approval_can_only_follow_awaiting_approval(status: BookingStatus) -> None:
    assert can_transition(status, S.APPROVED) is (status == S.AWAITING_APPROVAL)


@pytest.mark.parametrize("status", list(BookingStatus))
def test_booking_can_only_follow_revalidation(status: BookingStatus) -> None:
    assert can_transition(status, S.BOOKING) is (status == S.REVALIDATION)


@pytest.mark.parametrize("status", list(BookingStatus))
def test_confirmation_can_only_follow_booking(status: BookingStatus) -> None:
    assert can_transition(status, S.CONFIRMED) is (status == S.BOOKING)


@pytest.mark.parametrize("status", list(BookingStatus))
def test_revalidation_can_only_follow_approval(status: BookingStatus) -> None:
    assert can_transition(status, S.REVALIDATION) is (status == S.APPROVED)


@pytest.mark.parametrize("status", [S.APPROVED, S.REVALIDATION])
def test_a_changed_quote_sends_an_approved_intent_back_to_awaiting_approval(
    status: BookingStatus,
) -> None:
    assert can_transition(status, S.AWAITING_APPROVAL) is True


def test_an_ambiguous_booking_outcome_goes_to_needs_review_not_failed_or_retry() -> None:
    assert allowed_next(S.BOOKING) == frozenset({S.CONFIRMED, S.FAILED, S.NEEDS_REVIEW})
    assert can_transition(S.NEEDS_REVIEW, S.BOOKING) is False
    assert can_transition(S.FAILED, S.BOOKING) is False


def test_require_transition_names_both_statuses_in_the_error() -> None:
    with pytest.raises(InvalidTransitionError, match="DRAFT to APPROVED"):
        require_transition(S.DRAFT, S.APPROVED)


def test_require_transition_does_not_raise_for_an_allowed_change() -> None:
    require_transition(S.DRAFT, S.QUOTED)


def test_invalid_transition_is_a_domain_error() -> None:
    assert issubclass(InvalidTransitionError, DomainError)


# --- BookingIntent -----------------------------------------------------------

INTENT_ID = "11111111-1111-4111-8111-111111111111"
TRIP_ID = "22222222-2222-4222-8222-222222222222"
QUOTE_ID = "33333333-3333-4333-8333-333333333333"
CREATED = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def intent_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": INTENT_ID,
        "trip_id": TRIP_ID,
        "quote_id": QUOTE_ID,
        "idempotency_key": "client-key-1",
        "created_at": CREATED,
    }
    data.update(overrides)
    return data


def test_a_new_intent_starts_as_a_draft() -> None:
    intent = BookingIntent.model_validate(intent_data())

    assert intent.status is S.DRAFT
    assert str(intent.quote_id) == QUOTE_ID


def test_transition_to_returns_a_new_intent_and_leaves_the_old_one_alone() -> None:
    draft = BookingIntent.model_validate(intent_data())

    quoted = draft.transition_to(S.QUOTED)

    assert quoted.status is S.QUOTED
    assert draft.status is S.DRAFT
    assert quoted.id == draft.id
    assert quoted.idempotency_key == draft.idempotency_key


def test_the_mvp_path_reaches_approved_step_by_step() -> None:
    intent = BookingIntent.model_validate(intent_data())

    for target in (S.QUOTED, S.AWAITING_APPROVAL, S.APPROVED):
        intent = intent.transition_to(target)

    assert intent.status is S.APPROVED


@pytest.mark.parametrize("target", [S.APPROVED, S.BOOKING, S.CONFIRMED, S.REVALIDATION])
def test_a_draft_cannot_skip_ahead(target: BookingStatus) -> None:
    draft = BookingIntent.model_validate(intent_data())

    with pytest.raises(InvalidTransitionError):
        draft.transition_to(target)
    assert draft.status is S.DRAFT


def test_an_approved_intent_cannot_jump_straight_to_booking() -> None:
    approved = BookingIntent.model_validate(intent_data(status="APPROVED"))

    with pytest.raises(InvalidTransitionError):
        approved.transition_to(S.BOOKING)


def test_a_cancelled_intent_cannot_be_revived() -> None:
    cancelled = BookingIntent.model_validate(intent_data(status="CANCELLED"))

    for target in BookingStatus:
        with pytest.raises(InvalidTransitionError):
            cancelled.transition_to(target)


@pytest.mark.parametrize("field", ["id", "trip_id", "quote_id"])
def test_intent_ids_must_be_uuids(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        BookingIntent.model_validate(intent_data(**{field: "nope"}))


@pytest.mark.parametrize("key", ["", "   "])
def test_idempotency_key_must_not_be_blank(key: str) -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        BookingIntent.model_validate(intent_data(idempotency_key=key))


def test_intent_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        BookingIntent.model_validate(intent_data(created_at=datetime(2026, 11, 1, 9, 0)))


def test_an_intent_has_no_place_for_provider_booking_results() -> None:
    for field in ("provider_reference", "confirmation_code", "payment"):
        with pytest.raises(ValidationError, match=field):
            BookingIntent.model_validate(intent_data(**{field: "x"}))


def test_intent_is_immutable_so_status_only_changes_through_the_table() -> None:
    intent = BookingIntent.model_validate(intent_data())

    with pytest.raises(ValidationError, match="frozen"):
        intent.status = S.CONFIRMED


def test_intent_json_round_trip() -> None:
    intent = BookingIntent.model_validate(intent_data(status="QUOTED"))

    assert BookingIntent.model_validate_json(intent.model_dump_json()) == intent
    assert intent.model_dump(mode="json")["status"] == "QUOTED"


# --- Approval ----------------------------------------------------------------

APPROVED_AT = datetime(2026, 11, 1, 9, 5, tzinfo=UTC)
EXPIRES_AT = APPROVED_AT + timedelta(minutes=15)
HASH = "a1b2c3"


def approval_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "44444444-4444-4444-8444-444444444444",
        "booking_intent_id": INTENT_ID,
        "approver_id": "owner-1",
        "quote_content_hash": HASH,
        "approved_at": APPROVED_AT,
        "expires_at": EXPIRES_AT,
    }
    data.update(overrides)
    return data


def test_valid_approval() -> None:
    approval = Approval.model_validate(approval_data())

    assert approval.approver_id == "owner-1"
    assert approval.quote_content_hash == HASH
    assert approval.expires_at - approval.approved_at == timedelta(minutes=15)


@pytest.mark.parametrize("expires", [APPROVED_AT, APPROVED_AT - timedelta(seconds=1)])
def test_an_approval_must_expire_after_it_was_given(expires: datetime) -> None:
    with pytest.raises(ValidationError, match="expire after it was given"):
        Approval.model_validate(approval_data(expires_at=expires))


@pytest.mark.parametrize("field", ["approver_id", "quote_content_hash"])
@pytest.mark.parametrize("value", ["", "  "])
def test_approver_and_hash_must_not_be_blank(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        Approval.model_validate(approval_data(**{field: value}))


@pytest.mark.parametrize("field", ["approved_at", "expires_at"])
def test_approval_times_must_be_timezone_aware(field: str) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Approval.model_validate(approval_data(**{field: datetime(2026, 11, 1, 9, 30)}))


def test_approval_is_expired_from_the_moment_it_expires() -> None:
    approval = Approval.model_validate(approval_data())

    assert approval.is_expired(EXPIRES_AT - timedelta(seconds=1)) is False
    assert approval.is_expired(EXPIRES_AT) is True
    assert approval.is_expired(EXPIRES_AT + timedelta(days=1)) is True


def test_approval_covers_the_exact_quote_it_was_given_for_while_unexpired() -> None:
    approval = Approval.model_validate(approval_data())

    assert approval.covers(HASH, EXPIRES_AT - timedelta(seconds=1)) is True


def test_approval_never_covers_a_changed_quote() -> None:
    approval = Approval.model_validate(approval_data())
    just_before = EXPIRES_AT - timedelta(seconds=1)

    assert approval.covers("a1b2c4", just_before) is False
    assert approval.covers(HASH.upper(), just_before) is False
    assert approval.covers("", just_before) is False
    assert approval.covers(HASH + " ", just_before) is False


def test_approval_never_covers_anything_once_expired() -> None:
    approval = Approval.model_validate(approval_data())

    assert approval.covers(HASH, EXPIRES_AT) is False
    assert approval.covers(HASH, EXPIRES_AT + timedelta(hours=1)) is False


def test_the_clock_value_must_be_timezone_aware() -> None:
    approval = Approval.model_validate(approval_data())

    with pytest.raises(ValueError, match="timezone-aware"):
        approval.covers(HASH, datetime(2026, 11, 1, 9, 6))
    with pytest.raises(ValueError, match="timezone-aware"):
        approval.is_expired(datetime(2026, 11, 1, 9, 6))


def test_approval_has_no_field_to_extend_or_override_its_own_validity() -> None:
    for field in ("valid", "revalidated", "booking_enabled"):
        with pytest.raises(ValidationError, match=field):
            Approval.model_validate(approval_data(**{field: True}))


def test_approval_is_immutable() -> None:
    approval = Approval.model_validate(approval_data())

    with pytest.raises(ValidationError, match="frozen"):
        approval.expires_at = EXPIRES_AT + timedelta(days=365)


def test_approval_json_round_trip() -> None:
    approval = Approval.model_validate(approval_data())

    assert Approval.model_validate_json(approval.model_dump_json()) == approval
