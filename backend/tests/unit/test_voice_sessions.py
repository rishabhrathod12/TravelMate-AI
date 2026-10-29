"""Voice session service: expiry, idle timeout, ownership and limits (Step B). No real time."""

from datetime import UTC, datetime, timedelta

import pytest

from app.voice.errors import SessionExpired, SessionNotFound, VoiceLimitExceeded
from app.voice.sessions import VoiceLimits, VoiceSessionService

START = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: int) -> None:
        self.now += timedelta(**delta)


def make(
    *, max_seconds: int = 600, idle: int = 120, active: int = 1, daily: int = 3
) -> tuple[VoiceSessionService, Clock]:
    clock = Clock()
    service = VoiceSessionService(VoiceLimits(max_seconds, idle, active, daily), clock)
    return service, clock


class TestLimitsObject:
    @pytest.mark.parametrize("args", [(0, 1, 1, 1), (10, 0, 1, 1), (10, 5, 0, 1), (10, 5, 1, 0)])
    def test_every_limit_must_be_positive(self, args: tuple[int, int, int, int]) -> None:
        with pytest.raises(ValueError, match="positive"):
            VoiceLimits(*args)

    def test_idle_cannot_exceed_the_session_limit(self) -> None:
        with pytest.raises(ValueError, match="idle"):
            VoiceLimits(60, 120, 1, 1)


class TestCreate:
    def test_a_session_has_an_unguessable_id_and_an_absolute_expiry(self) -> None:
        service, _ = make(max_seconds=600)

        first, second = service.create("a"), make()[0].create("a")

        assert len(first.id) >= 40 and first.id != second.id
        assert first.owner == "a"
        assert first.created_at == START
        assert first.expires_at == START + timedelta(seconds=600)
        assert first.last_activity_at == START

    def test_an_owner_is_required(self) -> None:
        with pytest.raises(ValueError, match="owner"):
            make()[0].create("  ")

    def test_the_concurrent_limit_applies_per_owner(self) -> None:
        service, _ = make(active=1)
        service.create("a")

        with pytest.raises(VoiceLimitExceeded) as raised:
            service.create("a")

        assert raised.value.kind == "active"
        service.create("b")  # another owner is not affected

    def test_ending_a_session_frees_the_concurrent_slot(self) -> None:
        service, _ = make(active=1)
        session = service.create("a")

        service.end(session.id, "a")

        assert service.create("a").id != session.id

    def test_an_expired_session_no_longer_counts_as_active(self) -> None:
        service, clock = make(active=1, max_seconds=60, idle=60)
        service.create("a")
        clock.advance(seconds=61)

        service.create("a")

        assert service.active_count("a") == 1

    def test_the_daily_limit_counts_sessions_even_after_they_end(self) -> None:
        service, _ = make(active=5, daily=2)
        for _ in range(2):
            service.end(service.create("a").id, "a")

        with pytest.raises(VoiceLimitExceeded) as raised:
            service.create("a")

        assert raised.value.kind == "daily"

    def test_the_daily_limit_resets_on_the_next_utc_day(self) -> None:
        service, clock = make(active=5, daily=1)
        service.end(service.create("a").id, "a")
        clock.now = datetime(2026, 12, 2, 0, 0, 1, tzinfo=UTC)

        assert service.create("a").owner == "a"


class TestExpiry:
    def test_a_session_expires_at_the_absolute_limit_even_with_activity(self) -> None:
        service, clock = make(max_seconds=300, idle=120)
        session = service.create("a")
        for _ in range(4):
            clock.advance(seconds=70)
            service.touch(session.id, "a")

        clock.advance(seconds=70)  # 350 s in: past the absolute limit, though just active

        with pytest.raises(SessionExpired):
            service.get(session.id, "a")

    def test_touching_never_extends_the_absolute_expiry(self) -> None:
        service, clock = make(max_seconds=300, idle=120)
        session = service.create("a")
        clock.advance(seconds=100)

        assert service.touch(session.id, "a").expires_at == session.expires_at

    def test_an_idle_session_expires_and_activity_restarts_the_idle_timer(self) -> None:
        service, clock = make(max_seconds=600, idle=120)
        kept = service.create("a")
        clock.advance(seconds=100)
        service.touch(kept.id, "a")
        clock.advance(seconds=100)

        assert service.get(kept.id, "a").id == kept.id  # 100 s since activity: still live
        clock.advance(seconds=21)
        with pytest.raises(SessionExpired):
            service.get(kept.id, "a")
        assert service.active_count("a") == 0

    def test_an_expired_session_is_removed_so_the_next_lookup_is_not_found(self) -> None:
        service, clock = make(max_seconds=60, idle=60)
        session = service.create("a")
        clock.advance(seconds=60)

        with pytest.raises(SessionExpired):
            service.get(session.id, "a")
        with pytest.raises(SessionNotFound):
            service.get(session.id, "a")

    def test_touching_an_expired_session_fails(self) -> None:
        service, clock = make(max_seconds=60, idle=60)
        session = service.create("a")
        clock.advance(seconds=61)

        with pytest.raises(SessionExpired):
            service.touch(session.id, "a")


class TestOwnership:
    def test_another_owner_gets_not_found_for_get_touch_and_end(self) -> None:
        service, _ = make(active=2)
        session = service.create("a")

        for action in (service.get, service.touch, service.end):
            with pytest.raises(SessionNotFound):
                action(session.id, "b")

        assert service.get(session.id, "a").id == session.id  # still there for the owner

    def test_not_found_looks_the_same_for_a_missing_id_and_someone_elses(self) -> None:
        service, _ = make()
        session = service.create("a")

        with pytest.raises(SessionNotFound) as other:
            service.get(session.id, "b")
        with pytest.raises(SessionNotFound) as missing:
            service.get("does-not-exist-at-all", "a")

        assert str(other.value) == str(missing.value)
        assert session.id not in str(other.value)

    def test_ending_removes_the_session(self) -> None:
        service, _ = make()
        session = service.create("a")

        service.end(session.id, "a")

        with pytest.raises(SessionNotFound):
            service.get(session.id, "a")
        with pytest.raises(SessionNotFound):
            service.end(session.id, "a")
