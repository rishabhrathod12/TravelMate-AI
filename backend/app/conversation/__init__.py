"""Turning what a traveller says into a valid trip request (docs/VOICE_ASSISTANT_PLAN.md, V5).

This package is deliberately separate from the voice transport: it takes text and returns text,
so typed chat and a future speech-to-text front end can share it. Rules it keeps:
- A detail is accepted only if the traveller's own words support it. The language model proposes
  details together with the exact words it relied on, and code checks those words against what
  was said. Nothing the model says is trusted on its own.
- Dates must be explicit. "Tomorrow", "next Friday" and "kal" are never turned into a date; the
  traveller is asked for a day and month. Code, not the model, reads the date.
- The traveller's message is untrusted data, passed to the model only inside a delimited block.
  The model has no tools, and nothing here can book, approve or pay.
- The domain's own validation has the final say on whether a request is valid.
"""
