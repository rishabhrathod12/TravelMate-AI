class VoiceError(Exception):
    """Base class for voice session errors. Messages never contain session IDs or owners."""


class SessionNotFound(VoiceError):
    """No such session for this owner. Another owner's session looks exactly the same."""


class SessionExpired(VoiceError):
    """The session ran past its time limit or sat idle too long."""


class VoiceLimitExceeded(VoiceError):
    """The owner reached a configured limit. `kind` is "active" or "daily"."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"the {kind} voice session limit has been reached")
        self.kind = kind


class VoiceToolNotAllowed(VoiceError):
    """A tool name that is not on the voice allow-list."""
