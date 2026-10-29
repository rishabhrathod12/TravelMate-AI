"""The LLM layer: a replaceable client interface, a fake for tests, and the itinerary drafter.

Rules this package keeps (SECURITY §3, ARCHITECTURE §2, PRD AC-07):
- The LLM is reached only through `LLMClient`. Nothing outside `app.llm` imports a
  vendor SDK, and no SDK is installed today.
- The model is given no tools. A request carries messages and limits, nothing else.
- Untrusted text (provider names, reviews, user notes) is passed only as delimited
  data, and the model's answer must be structured and validated before use.
- The model never produces prices, availability or dates as facts, and nothing it
  says can change a booking or an approval: this package imports no booking code.
- Tests use `FakeLLMClient`. No test and no default code path makes a network call.
"""
