"""Masking secrets and personal data before anything is logged (SECURITY §9, PRD AC-08).

Three independent layers, because any one of them can miss:
1. By field name: a value stored under a key that looks like a secret or personal data is masked
   whatever it contains (`api_key`, `Authorization`, `password`, `traveller_name`, ...).
2. By known value: the exact secret values this process holds (for example the API key) are masked
   wherever they appear in a string, even inside an exception message.
3. By shape: bearer tokens, `sk-...` style keys, connection strings with a password and private-key
   blocks are masked even if nobody told us about them.
"""

import re
from collections.abc import Iterable, Mapping

MASK = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"secret|token|passw|credential|authorization|cookie|api[_-]?key|private[_-]?key|\bkey\b"
    r"|_key$|^key_|traveller|passenger|email|phone|birth|passport",
    re.IGNORECASE,
)
_SHAPES = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@[^\s]+"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S
    ),
)
_MIN_SECRET_LENGTH = 4


def is_sensitive_key(name: str) -> bool:
    return _SENSITIVE_KEY.search(name) is not None


class Redactor:
    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        # Longest first, so a secret that contains another is masked whole.
        self._secrets = sorted(
            {value for value in secret_values if len(value.strip()) >= _MIN_SECRET_LENGTH},
            key=len,
            reverse=True,
        )

    def text(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, MASK)
        for shape in _SHAPES:
            value = shape.sub(MASK, value)
        return value

    def value(self, value: object, *, key: str | None = None) -> object:
        """Mask `value`, recursing into containers. A sensitive key masks the whole value."""
        if key is not None and is_sensitive_key(key):
            return MASK
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Mapping):
            return {str(k): self.value(v, key=str(k)) for k, v in value.items()}
        if isinstance(value, list | tuple | set | frozenset):
            return [self.value(item) for item in value]
        if value is None or isinstance(value, bool | int | float):
            return value
        return self.text(str(value))
