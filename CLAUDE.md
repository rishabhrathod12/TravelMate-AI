# CLAUDE.md — Working rules for TravelMate AI

## Before significant work
- Read `docs/PRD.md`, `docs/ARCHITECTURE.md` and `docs/SECURITY.md`.
- Check `docs/IMPLEMENTATION_PLAN.md` to confirm which milestone is active. Do not start a later milestone without approval.
- Run `git status` first and preserve any uncommitted user work.

## How to change code
- Prefer small, testable changes. Add or update tests with each behaviour change.
- Follow the dependency rules in `docs/ARCHITECTURE.md` §3. In particular, `workflow/` must never import `booking/`.
- Target Python 3.12. Use the stack in `docs/ADR/0001-approved-stack.md`.
- Do not silently change architecture decisions. If a change conflicts with an ADR or a core document, stop, explain the conflict, and record a new ADR or ask.

## Data integrity
- Never invent live travel data: no fares, schedules, availability, weather or hotel facts that did not come from a provider or a labelled MOCK fixture.
- Every provider-derived value carries provenance: `LIVE`, `CACHED_LIVE` or `MOCK`. Never label mock data as live.
- Store money as integer minor units with a currency code. Do not use floats for money.

## Booking and payments
- Never execute a real booking or payment without explicit authorization from the project owner and a human approval flow for the specific quote.
- Do not claim a booking succeeded unless a provider confirmation has been received and validated. Do not claim it without verification.
- `BOOKING_ENABLED` stays `false` unless the project owner has authorized enablement.

## Secrets
- Never print, log, or commit secret values or `.env` contents.
- Never commit `.env`. `.env.example` holds names and placeholders only.
- Do not make external API calls, including to the LLM provider, unless the task explicitly requires it and the key is supplied by the user through the environment.

## Testing and reporting
- Run the relevant tests after changes and report the actual results, including failures, skipped tests, and anything not run.
- Verify each changed file by reading it back after writing it.
- Tests must not require network access or real API keys.

## Git
- Do not commit or push unless asked.
- Keep the working tree clean between tasks, and report what changed.
- Do not rewrite or delete history.

## Collaboration
- Stop and wait for review at the end of each milestone.
- Record unresolved assumptions in `docs/PRD.md` §10–11 rather than inventing answers.
