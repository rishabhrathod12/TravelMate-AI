"""Voice session foundation (docs/VOICE_ASSISTANT_PLAN.md, ADR 0002).

Only the parts that need no vendor: short-lived sessions with limits and an allow-list of the
tools a voice conversation may ever use. Nothing here carries audio, talks to a provider or can
touch booking. Nothing in this package may import booking, workflow internals or a network
library (an architecture test enforces it).
"""
