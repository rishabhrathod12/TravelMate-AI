"""Request ids and safe structured logging (SECURITY §9, PRD NFR-05, AC-08).

- Every request has an id, taken from the caller if it looks safe, otherwise made up.
- Logs are JSON, carry the request id, and pass through a redaction filter that masks secrets by
  field name, by known value and by common token shapes.
- Logs never hold full prompts, provider responses, traveller details or exception text that has
  not been redacted. They record sizes, statuses, ids and timings.
"""
