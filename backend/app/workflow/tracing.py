"""Refuse to run with third-party tracing switched on.

LangGraph brings in LangSmith, LangChain's tracing client. If tracing is enabled by an environment
variable it sends every run's inputs and outputs to LangChain's servers: trip details, option data
and model prompts. That is third-party processing the owner has not approved (SECURITY §7, §9), so a
workflow refuses to start while any tracing switch is on. Nothing in this project turns one on.
"""

from collections.abc import Mapping

TRACING_SWITCHES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)
_TRUE = {"1", "true", "yes", "on"}


class ThirdPartyTracingEnabled(RuntimeError):
    """A tracing switch is on, so run data would leave the machine."""


def refuse_third_party_tracing(environment: Mapping[str, str]) -> None:
    for name in TRACING_SWITCHES:
        if environment.get(name, "").strip().casefold() in _TRUE:
            raise ThirdPartyTracingEnabled(
                f"{name} is switched on: it would send run data to a third party. "
                "Unset it to run the planning workflow."
            )
