"""Short-lived voice sessions held in memory (no database exists yet, PRD plan M9).

A session is an opaque random ID owned by one person. Every read checks the owner: the ID alone
is never enough (SECURITY §2). A session ends at an absolute time limit, after an idle period,
or when its owner ends it. Limits come from explicit settings; there are no defaults here.
Sessions are lost on restart. The clock is injected so tests never wait.
"""

import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from pydantic import Field

from app.config import Settings
from app.domain.base import DomainModel
from app.domain.timeutil import UtcDateTime
from app.voice.errors import SessionExpired, SessionNotFound, VoiceLimitExceeded


@dataclass(frozen=True)
class VoiceLimits:
    max_seconds: int
    idle_seconds: int
    max_active_per_owner: int
    max_per_day_per_owner: int

    def __post_init__(self) -> None:
        values = (
            self.max_seconds,
            self.idle_seconds,
            self.max_active_per_owner,
            self.max_per_day_per_owner,
        )
        if any(value < 1 for value in values):
            raise ValueError("every voice limit must be a positive whole number")
        if self.idle_seconds > self.max_seconds:
            raise ValueError("the idle limit cannot exceed the session time limit")

    @classmethod
    def from_settings(cls, settings: Settings) -> "VoiceLimits":
        values = (
            settings.voice_session_max_seconds,
            settings.voice_session_idle_seconds,
            settings.voice_max_active_sessions_per_owner,
            settings.voice_max_sessions_per_day_per_owner,
        )
        if any(value is None for value in values):
            raise ValueError("voice limits are not all set")
        max_seconds, idle_seconds, active, daily = (int(value or 0) for value in values)
        return cls(max_seconds, idle_seconds, active, daily)


class VoiceSession(DomainModel):
    id: str = Field(min_length=16)
    owner: str = Field(min_length=1)
    created_at: UtcDateTime
    expires_at: UtcDateTime
    last_activity_at: UtcDateTime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class VoiceSessionService:
    def __init__(self, limits: VoiceLimits, clock: Callable[[], datetime] = _utc_now) -> None:
        self._limits = limits
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: dict[str, VoiceSession] = {}
        # Creation times per owner, kept for the daily limit even after a session ends.
        self._created: dict[str, list[datetime]] = {}

    @property
    def limits(self) -> VoiceLimits:
        return self._limits

    def _is_over(self, session: VoiceSession, now: datetime) -> bool:
        idle = timedelta(seconds=self._limits.idle_seconds)
        return now >= session.expires_at or now - session.last_activity_at >= idle

    def _purge(self, now: datetime) -> None:
        for session_id in [i for i, s in self._sessions.items() if self._is_over(s, now)]:
            del self._sessions[session_id]
        today = now.date()
        for owner in list(self._created):
            kept = [moment for moment in self._created[owner] if moment.date() >= _yesterday(today)]
            if kept:
                self._created[owner] = kept
            else:
                del self._created[owner]

    def create(self, owner: str) -> VoiceSession:
        if not owner.strip():
            raise ValueError("a voice session needs an owner")
        with self._lock:
            now = self._clock()
            self._purge(now)
            active = sum(1 for s in self._sessions.values() if s.owner == owner)
            if active >= self._limits.max_active_per_owner:
                raise VoiceLimitExceeded("active")
            created_today = sum(1 for m in self._created.get(owner, []) if m.date() == now.date())
            if created_today >= self._limits.max_per_day_per_owner:
                raise VoiceLimitExceeded("daily")

            session = VoiceSession(
                id=secrets.token_urlsafe(32),
                owner=owner,
                created_at=now,
                expires_at=now + timedelta(seconds=self._limits.max_seconds),
                last_activity_at=now,
            )
            self._sessions[session.id] = session
            self._created.setdefault(owner, []).append(now)
            return session

    def get(self, session_id: str, owner: str) -> VoiceSession:
        """The owner's live session. Someone else's, or a missing one, is "not found"."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner != owner:
                raise SessionNotFound("no such voice session")
            if self._is_over(session, self._clock()):
                del self._sessions[session_id]
                raise SessionExpired("the voice session has ended")
            return session

    def touch(self, session_id: str, owner: str) -> VoiceSession:
        """Record activity so the idle timer restarts. It never extends the absolute limit."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner != owner:
                raise SessionNotFound("no such voice session")
            now = self._clock()
            if self._is_over(session, now):
                del self._sessions[session_id]
                raise SessionExpired("the voice session has ended")
            refreshed = session.model_copy(update={"last_activity_at": now})
            self._sessions[session_id] = refreshed
            return refreshed

    def end(self, session_id: str, owner: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner != owner:
                raise SessionNotFound("no such voice session")
            del self._sessions[session_id]

    def active_count(self, owner: str) -> int:
        with self._lock:
            self._purge(self._clock())
            return sum(1 for s in self._sessions.values() if s.owner == owner)


def _yesterday(today: date) -> date:
    return today - timedelta(days=1)
