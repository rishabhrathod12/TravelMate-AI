# TravelMate AI: project context

A short brief for starting a new working session. Update only the lines marked **UPDATE** after each commit; the rest rarely changes. It summarises the other documents and does not replace them: the PRD, ARCHITECTURE, SECURITY, the implementation plan and `CLAUDE.md` are the sources of truth.

## Project
- An Agentic AI travel planner, built as a portfolio project to learn Agentic AI engineering.
- Backend: Python 3.12, FastAPI, Pydantic v2, strict mypy, Ruff. Frontend: React 19, TypeScript, Vite.
- Planned and **not built**: LangGraph, a live LLM, PostgreSQL use, live providers, authentication, any booking.
- Repository: github.com/rishabhrathod12/TravelMate-AI, branch `main`.

## Current state (UPDATE after every commit)
- Last pushed commit: `f2f29f4` (voice Step B; includes M6 at `803f9d6`, voice Step A, and transport categories with demo booking at `5401234`). CI passed for `f2f29f4`, as reported by the owner; the run was not read by Claude. The owner also reported CI passed for `5401234`. CI results for the other intermediate pushes (`0ad3730`, `afd22b4`, `32902cb`, `9345603`) were not reported to Claude. Local commits made after this file was written are not covered.
- Tests: at `803f9d6`, 1084 backend tests pass (run locally on Python 3.12.10 on 2026-10-29). The last recorded frontend count is 142 at `b950e13` and was not re-run. At `803f9d6` (checked 2026-10-29, Python 3.12.10): `ruff check` passes, `ruff format --check` finds 85 files already formatted, and strict `mypy app` reports no issues in 47 source files. Mypy covers `app/` only, not the tests.
- **Complete:** M0.
- **Implemented, awaiting owner review:** M1 to M6. Each is "not closed" in the plan's status table. Open items: M1 (Docker and PostgreSQL start, production-secrets guard), M2 (`budget` on `TripRequest`), and the Q9 to Q19 decisions below.
- **M11 is a frontend prototype only**, built with hand-written demo data labelled MOCK. The only real endpoint it calls is `GET /health`.
- **Voice session foundation, "Step B" (2026-10-30, committed and pushed as `f2f29f4`):** `backend/app/voice/` and `backend/app/api/voice.py` add short-lived in-memory voice sessions (absolute expiry, idle timeout, owner checks, concurrent and daily limits) and a read-only tool allow-list, behind `VOICE_ENABLED` (off by default, explicit `VOICE_*` limits required, refuses to start in production, acts as the configured `VOICE_DEV_PRINCIPAL` because PRD Q4 auth does not exist). No vendor, key or audio. Backend 1207 tests, ruff, ruff format and mypy clean on 2026-10-30. SECURITY §12 describes it.
- **Voice Step B2 (2026-10-30, uncommitted):** a development-only "session-only" voice adapter (`VITE_VOICE_ADAPTER=session` in the shell that runs `npm run dev`) opens real backend voice sessions from the Step A screen. It hears and plays nothing, never asks for the microphone, and says so on screen. Adds a typed API client, a `/api` dev proxy, and backend `POST …/sessions/{id}/activity`. Backend 1210 tests and frontend 309 tests pass; lint, typecheck, build, ruff and mypy clean. Not checked in a real browser.
- **Transport categories and demo booking (2026-10-30, ADR 0003, PRD FR-18):** the mock transport provider now returns seven fictional services for Indore to Goa (3 flights, 2 trains, 2 buses, all MOCK) with operator, service label and mode-specific details. The Plan page groups them by mode, sorts, and compares up to three side by side. A separate, labelled **simulated booking** ("DEMO — NOT A REAL BOOKING", reference `DEMO-BOOKING-001`) exists in `frontend/src/demoBooking/`. It is in-memory, frontend-only, makes no network call, and is unrelated to the real booking lifecycle, which stays disabled. The frontend reads its flight/train/bus templates from `frontend/src/demo/transportFixtures.json`, generated from the backend fixtures by `backend/scripts/export_demo_fixtures.py` (a backend test fails if it is stale). Checked 2026-10-30: backend 1110 tests, ruff, ruff format and mypy clean; frontend lint, typecheck, build clean and 271 tests pass. Not checked: a real browser, 375 px, keyboard-only, screen reader.
- **M6 (itinerary drafter and LLM interface)** is committed with fakes only, including 106 prompt-injection tests. No live model call has ever been made, no vendor SDK is installed, and the OpenAI adapter has no real transport.
- **Pending:** M7, M8, M9, M10, M12.
- **Blocked on the owner's authorization:** M13 (live providers) and M14 (booking execution).
- Real booking is disabled and must stay disabled (`BOOKING_ENABLED` must be false).
- **Unverified:**
  - Docker and PostgreSQL start (Docker is not installed on the development machine).
  - The production-secrets startup guard (not built; planned for M9).
  - The frontend has not been checked visually in a browser.
  - The OpenAI wire format against the live API.

## Decided by the owner (UPDATE as questions are answered)
- A trip request has an explicit `trip_type` (`ONE_WAY` or `ROUND_TRIP`). A same-day return is a round trip with the same date.
- The `budget` field and the `preferences` length cap are deferred. There is no traveller upper limit yet.
- The frontend prototype was approved, built ahead of the API, with demo data labelled MOCK.
- (Add each answered question here.)

## Open decisions (UPDATE as they are answered; defaults are in PRD §10 and §11)
- Q9: does an expired approval make the intent EXPIRED, or send it back to AWAITING_APPROVAL?
- Q10: may a booking in flight, or an unclear one, be cancelled or expired, and how are FAILED and NEEDS_REVIEW resolved?
- Q11: are there two idempotency keys (creation and per booking attempt)?
- Q12: what does a quoted price cover (per traveller, per party, per night)?
- Q13: stay, weather and itinerary rules for one-way and same-day trips.
- Q14: traveller and text limits, budget rules, rooms.
- Q15: how a quote's content hash is built.
- Q16: the label for a mix of LIVE and CACHED_LIVE.
- Q17: what "within budget" means.
- Q18: contingency percentage, base and rounding, and the local transport allowance.
- Q19: the language model, token limit, timeout, prompt-size limit and who supplies the API key.
- Provisional assumptions A5 to A13 need review.
- Also: review the `tzdata` dependency, and the two open M1 criteria (Docker and PostgreSQL, secrets guard).

## Working rules (rarely change)
- Read `CLAUDE.md` and `docs/` first. Stop at the end of each milestone.
- Never commit or push without the owner's explicit approval.
- Never invent live data. Label every provider value LIVE, CACHED_LIVE or MOCK. Money is integer minor units plus a currency code.
- Do not silently resolve open decisions: list them with a recommendation, and ask only what blocks safe work.
- Human approval is required before any real booking or payment. No secrets in files, logs or output.

## Environment notes
- Windows. The owner's shell may have the `aitravel` virtual environment active, so call `backend/.venv/Scripts/python.exe` by absolute path. It is Python 3.12.10, but the test suite has not been run in it yet.
- `aitravel` was rebuilt on Python 3.12.10 on 2026-10-29 (it was 3.14, which the project rejects) and the full backend suite passed in it. Use it as a fallback and do not recreate it on 3.14.
- Docker is not installed. Open the frontend at `http://localhost:5173` (not `127.0.0.1`).
- Backend checks: `pytest backend/tests`, `ruff check`, `ruff format --check`, and `mypy` (run inside `backend/`).
- Frontend checks (in `frontend/`): `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.

## Next task (UPDATE)
- Owner reviews M6 (pushed, CI passed).
- Before M7 (the LangGraph workflow), the owner needs to rule on Q12, Q13, Q14 and Q18, and decide Q19 (model, limits, key) before any live LLM call.
- Connecting a real LLM needs three separate approvals: the `openai` dependency and a real transport, an owner-supplied key, and the first live call.
