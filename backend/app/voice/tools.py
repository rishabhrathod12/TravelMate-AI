"""The only tools a voice conversation may use (SECURITY §3, ARCHITECTURE §4).

A fixed allow-list of the read-only research tools. There is no booking, approval, payment or
demo-booking tool, and no way to add one by passing a name: anything not listed is refused,
exactly as written (no case folding, no trimming). Authority comes from this list in code, not
from what a model or a transcript says.
"""

from app.tools.research import GET_WEATHER, SEARCH_HOTELS, SEARCH_TRANSPORT, ToolSpec, tool_specs
from app.voice.errors import VoiceToolNotAllowed

ALLOWED_VOICE_TOOLS: frozenset[str] = frozenset({SEARCH_TRANSPORT, SEARCH_HOTELS, GET_WEATHER})


def require_allowed_tool(name: object) -> str:
    """Return the tool name if it is on the allow-list, otherwise raise."""
    if not isinstance(name, str) or name not in ALLOWED_VOICE_TOOLS:
        raise VoiceToolNotAllowed("that tool is not available to voice conversations")
    return name


def allowed_tool_specs() -> tuple[ToolSpec, ...]:
    """What a voice model may be shown: the read-only research tools and nothing else."""
    return tuple(spec for spec in tool_specs() if spec.name in ALLOWED_VOICE_TOOLS)
