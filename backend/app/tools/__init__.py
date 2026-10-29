"""Research tools: typed, read-only functions the workflow (and later an LLM) may call.

Tools wrap the provider interfaces (ARCHITECTURE §2, §4). They validate their
input, call the provider with bounded retries, record every call, and return typed
results with provenance. A failing provider becomes an error entry in the result,
not an exception, so one failure never hides the other categories (PRD AC-04).

No tool can create, change or confirm a booking, and none is registered with
booking code (ARCHITECTURE §4). Tools depend on provider interfaces only, never on
a concrete provider.
"""
