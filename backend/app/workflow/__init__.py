"""The planning workflow (plan M7, ARCHITECTURE §4 and §8): one resumable LangGraph graph.

    intake -> research (transport, hotels, weather in parallel) -> select -> itinerary
           -> cost -> summarise

- `intake` checks that the trip is complete and valid and pauses for clarification until it is.
  Missing inputs mean questions and no provider call at all (PRD AC-09).
- `research` runs the read-only tools. A failing provider becomes an error entry and never hides
  the others (PRD AC-04). A trip with no hotel stay (Q13) makes no hotel call.
- `select` pauses for the traveller to choose options.
- `itinerary` asks the model for a day-by-day draft through the `LLMClient` interface.
- `cost` is plain deterministic code (no model) following the owner's rules (Q12, Q13, Q18).
- `summarise` assembles the result.

Limits: a maximum number of graph steps, of tool calls and of human answers per run. Exceeding
one ends the run as `stopped_limit` (ARCHITECTURE §8, NFR-09).

This package is the only place that imports LangGraph. It has no tool, import or name that
reaches booking, approval or payment (ARCHITECTURE §4 rule 1). Nothing here is persisted yet: the
checkpointer is in memory until M9, and checkpoints are read back only through an allowlist of
this project's own types.
"""
