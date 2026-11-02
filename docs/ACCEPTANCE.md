# TravelMate AI: MVP acceptance record (Milestone 12)

Status: **Accepted by the project owner on 2026-11-02 as the record for a project complete at its current scope (PRD A23).** The gaps it lists stay true. Run on 2026-11-02 against commit `d21d1ce` plus the uncommitted M12 changes listed at the end. Plan: `docs/IMPLEMENTATION_PLAN.md` M12. Requirements: `docs/PRD.md` §8 and §9.

Every result below says how it was obtained. "Automated" means a test that runs in CI with no network and no key. "Manual" means a person or an agent ran it by hand and the evidence is described here, not committed as a test.

## 1. Result in one paragraph

Nine of ten acceptance criteria pass with automated evidence. **AC-10 (375 px, no horizontal scroll) passes by manual measurement only; there is no committed browser test. The project owner accepted that evidence on 2026-11-02** (section 3, PRD A20). No open high-severity finding is known to me, but that is not the same as a security review by someone else (section 6). Nothing in the MVP can book, pay, or reach a live provider or a live language model, and none of the evidence below used one.

## 2. What was run

| Check | Result |
|---|---|
| Backend tests | **2120 passed, 69 skipped** (the skipped tests need PostgreSQL; see CI row) |
| Backend `ruff check`, `ruff format --check`, `mypy` (99 source files, strict) | clean |
| Frontend tests (Vitest, includes 14 axe-core accessibility tests) | **422 passed** |
| Frontend `eslint`, `tsc --noEmit`, `vite build` | clean |
| CI, GitHub Actions, every push since the redesign (`7c876cd` to `be2a320`) | **all jobs succeeded** (backend, frontend, postgres, secret-scan), read from the GitHub API after each push. The last two runs (`d21d1ce`, `be2a320`) were checked after this record was first written. |
| CI `postgres` job (50 tests: migrations up and down, constraints, `audit_events` privileges, restricted-role API and booking flow) | **succeeded on `9b2f7db` and `308c5e8`.** It failed once, on the M10 commit `ccd3e23`, and `9b2f7db` fixed that. This closes the M9 and M10 criteria that could only be checked on SQLite locally. |

## 3. Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-01 Indore to Goa in mock mode returns transport, hotel, weather, itinerary and cost estimate | **Pass** | Automated: `contract/test_indore_goa_scenario.py` (providers) and `unit/test_workflow.py` (full workflow run). Also run by hand over HTTP against a live server ten times: each run reached `completed` with an estimate, an itinerary and weather. |
| AC-02 Every price, availability and weather value carries LIVE, CACHED_LIVE or MOCK | **Pass** | Automated: `unit/test_research_tools.py`, `unit/test_provenance*.py`. A mock provider's data must be labelled MOCK or it is rejected. The UI shows the label on every price. |
| AC-03 Estimate total equals the sum of its lines in integer minor units | **Pass** | Automated: `unit/test_estimator.py`, `test_rounding.py`, `test_cost.py` (checked against an independent fraction reference). |
| AC-04 A failing provider gives a partial result with an error entry | **Pass** | Automated: `unit/test_research_tools.py`, `unit/test_workflow.py`. |
| AC-05 With `BOOKING_ENABLED=false`, an intent is recorded and no booking client is called | **Pass** | Automated: `unit/test_booking_service.py` (spy client never called). By hand: `POST .../execute` answered `409 booking_disabled` on a live server. `BOOKING_ENABLED=true` refuses to start (`tests/test_config.py`). |
| AC-06 An approval for an expired or changed quote is rejected | **Pass for the mock re-check path** | Automated: `unit/test_booking_service.py`. The live re-check path belongs to M14 and does not exist. |
| AC-07 The LLM is reached only through `LLMClient`; tests use a fake and no network | **Pass** | Automated: `architecture/test_llm_imports.py` (only the transport imports the SDK). No test calls OpenAI. **No real model call has ever been made in this project.** |
| AC-08 No secret appears in logs, responses or repository files | **Pass** | Automated: `unit/test_logging.py`, including against a running uvicorn. CI `secret-scan` (gitleaks) succeeded on every push. Local scan of all 311 tracked files for key, token and private-key patterns: only deliberately fake test values and the documented throwaway CI database password. `.env` is not tracked. |
| AC-09 Missing inputs give clarification questions and no provider calls | **Pass** | Automated: `unit/test_workflow.py`. |
| AC-10 The planning flow works at 375 px without horizontal scrolling | **Pass by manual measurement; accepted by the owner (2026-11-02)** | Manual, headless Edge with mobile emulation at 375 px: home, conversation, trip form with results, and every server-planner panel (choices, estimate, itinerary, approval terms, approved, clarification) measured zero horizontal overflow and no touch target under 36 px. **Gap, accepted:** the PRD asks for a browser test and Playwright was not added (owner chose Vitest only). On 2026-11-02 the owner accepted this manual evidence instead (PRD A20). The measurements are not a committed test, so a layout regression would not fail CI; they should be repeated after any large layout change. |

## 4. Non-functional checks run in M12

| Requirement | Result | Evidence |
|---|---|---|
| NFR-07 mock plan under 10 s | **Pass** | Ten full plans over HTTP (create trip, run, choose options, estimate, itinerary): min 0.06 s, median 0.07 s, max 0.20 s. The itinerary step used the scripted stand-in, not a model, so a live model would add its own latency. Live targets are for after provider selection. |
| NFR-12 accessibility (WCAG 2.1 AA, core flow) | **Automated checks pass; manual checks not done** | axe-core 4.14.0 (owner-approved dev dependency): 14 Vitest tests, plus the same rules in a real browser including colour contrast on 12 screens at 1280 px and 375 px: 0 violations after two fixes. **Not done:** a screen-reader pass, a keyboard-only walkthrough by a person, manual zoom and reduced-motion checks, other browsers. Automated audits find only part of the real problems, so this is not a WCAG conformance claim. |
| NFR-02 booking off by default | **Pass** | See AC-05. |
| NFR-04 tests need no network or key | **Pass** | CI runs with no secrets. |

## 5. Security checks

- **Prompt injection (SECURITY §3, item 9):** the itinerary drafter has a suite across hotel names, weather text, place names and notes (106 tests). The plan writer, added later for the chat plan, had one injection test; M12 added `unit/test_plan_writer_injection.py` (58 tests): six hostile strings in the place name and in the notes stay inside the data block, cannot forge its markers or change the fields around them; a model that obeys is stopped (made-up prices, availability, opening times and booking claims are rejected after one repair; smuggled fields are rejected; no tool is offered). A deliberate break of the plan checker made 5 of these tests fail, so they can fail.
- **Approvals and booking authority:** architecture tests fail if any model, tool, workflow, voice, provider or conversation code imports booking or builds an approval. The 8 deliberate breakages recorded in M10 were each caught.
- **Dependency audit:** CI runs `pip-audit` (backend) and `npm audit --audit-level=high` (frontend) and succeeded on every push. Locally, `npm audit --omit=dev` reports 0 findings. Plain `npm audit` reports 11 moderate findings in `minimatch` inside the eslint toolchain: dev-only, not shipped, present before M12, accepted here. `pip-audit` is not installed on this machine, so the backend audit result is CI's.
- **CI hardening:** the four GitHub Actions in `.github/workflows/ci.yml` are now pinned to full commit SHAs (resolved from GitHub's API on 2026-11-02), each with its tag as a comment. **Verified:** the run for `be2a320`, the first with the pinned actions, succeeded in all four jobs, so each pin (`checkout`, `setup-python`, `setup-node`, `gitleaks-action`) resolves and works. The gitleaks action is free for personal repositories; if the repository moves to an organisation, its licence terms need review.

## 6. What this record does not establish

- **No independent review.** The checks above were run by the same agent that wrote the code. A person or another reviewer should read the booking approval path (`app/services/booking.py`) and the logging redaction before anyone relies on them.
- **No real provider, model, voice service or payment** has been used. Everything is mock or scripted.
- **PostgreSQL** was verified in CI, not on the development machine.
- **Real authentication does not exist** (PRD Q4). Every API call acts for one configured development principal.
- The 69 skipped backend tests are the PostgreSQL ones; their result is CI's.

## 7. Known limitations of the MVP

Product and data
- All transport, hotel and weather data is a labelled MOCK fixture for Indore and Goa; other places return nothing. No live provider exists (M13, PRD Q1 to Q3).
- The itinerary and the chat plan come from scripted stand-ins unless `LLM_LIVE_ENABLED` is switched on with a key. That path has never been exercised against the real API.
- Ratings are not modelled; cancellation terms are grouped only by presence. The browser does not compute a total for a booking quote; it shows the quoted price, its basis and fees.
- Hotel rooms per party must be given; there is no default (PRD Q14).

Safety and booking
- Booking, confirmation, payment and reconciliation do not exist (M14). `execute` always answers `409`. Approvals record agreement only.
- An intent that nobody reads is not expired by a background job; time is applied when it is read or approved. A read of an intent (`GET`) can therefore write a status change and an audit event. It is audited and atomic, but a read that writes is unusual.

Operation
- **No real authentication.** The planning API, voice and chat are development-only: they refuse to start in production, so a production build shows the voice button and message box switched off. The trip form and demo comparison stay reachable from the menu.
- Run checkpoints are in memory (no PostgreSQL checkpointer): a run in progress at a restart is marked failed. `provider_calls` rows are never written.
- The server-planner panels (clarification, itinerary editing, approval step) exist only in development builds.

Frontend
- Voice is a labelled mock or a session-only adapter; there is no audio and no voice provider (ADR 0002).
- No Playwright tests. The dark theme and the home screen were checked in headless Edge only.

## 8. M12 changes made (uncommitted when written)

`.github/workflows/ci.yml` (pinned actions), `backend/tests/unit/test_plan_writer_injection.py` (new), `docs/ACCEPTANCE.md` (this file), and the M12 status lines in `docs/IMPLEMENTATION_PLAN.md` and `docs/PROJECT_CONTEXT.md`.

## 9. Addendum: work after the M12 record (2026-11-02)

The acceptance results above were recorded at M12. These changes came after it. They are frontend-only, add no dependency, change no API contract and leave booking switched off.

- **Chat always shows the newest message.** The newest message used to land under the sticky composer. Measured before and after in a real browser at 375 px and 1280 px (111 px hidden before, a 13 px gap after).
- **Progressive replies.** Each reply is revealed gradually by the browser. This is a presentation effect: the server sends each reply whole, and the conversation says so on screen. It includes a Markdown renderer written without a dependency (raw HTML shown as text; only http and https links clickable), a Stop button for a pending reply, and a skip badge and Esc.
- **Planning from the conversation.** "Plan this trip" starts the existing planning workflow, asks for the number of rooms (never defaulted), and shows the options, the weather forecast, the cost estimate, the draft itinerary and the approval step inside the conversation. The weather had been returned by the API but shown nowhere.
- **Checks:** 584 frontend tests; axe-core 0 violations in a real browser (including colour contrast) at both widths on the planning screens; a real-browser run against the real backend recorded no booking-related request until the reader pressed "Get the terms to approve", and then only the terms were requested. Break-and-restore checks were run on the key guards.
- **Still true:** this path is development-only (no real authentication, PRD Q4), everything is MOCK, no real model or provider was used, and the gaps in section 6 stand. Workflow clarification questions are answered in the existing form, not in free text. Private taxi, broader natural-language understanding and budget are not built.

## 10. Addendum: private taxi (2026-11-02)

- Mock private taxis (sedan, SUV, van) priced per vehicle; the estimate uses enough vehicles of one type to seat the party and states the count (ADR 0007, PRD A24). Migration `0003`, additive OpenAPI change. Demo booking still excludes taxis; booking stays off; all data MOCK.
- Checks: backend 2177 passed, 70 skipped (PostgreSQL tests run only in CI); frontend 588 passed; lint, type checks and build clean; break-and-restore checks on the basis, the vehicle count and the workflow wiring. Real-browser and CI results are recorded separately when run.

## 11. Addendum: broader offline wording, Phase 3 (2026-11-02)

- Slices 1 to 4 of the feature-integration plan (PRD A25), all in `backend/app/conversation/`. Backend only; no frontend, API, database, dependency or booking change. All data is still MOCK and the stand-in is still pattern matching, not a model.
- **Fixed wrong values found by probing 20 phrasings:** "Indore to Goa 1 Dec 2 adults" used to set the return date to 2 December; "trip for two people" made "two people" the destination; "tomorrow" and "kal" became origins; a child was silently dropped from "2 adults and 1 child". Each has a regression test.
- **Two existing tests were changed on purpose, with the owner's approval of the behaviour:** `test_a_total_the_model_worked_out_is_refused` (claims) and its twin in the manager tests pinned that a total is never accepted. They now check that a total is accepted only when code reads the same number from the written parts, and that any other number is still refused. `test_a_sentence_is_not_mistaken_for_place_names` used to expect nothing from "I want to go to Goa"; it now expects the destination "Goa" and still nothing from "I want to go".
- **Checks:** backend 2289 tests passed and 70 skipped (the PostgreSQL ones, which run only in CI); ruff, format and mypy clean, with mypy run from `backend/` as CI does. Nine break-and-restore checks on the key rules; one was not caught at first (number words as places) and a test was added until it was. A real-browser run against the real backend at 375 px and 1280 px read five new phrasings as expected, with no overflow and no axe violations.
- **Not done:** more relative dates and Hinglish place order (slice 5, skipped by the owner); an unspaced "Indore-Goa" (it would split "Port-Blair"); infants are never counted, they make the chat ask. Not independently reviewed, like the rest of the project.

## 12. Addendum: interface wording (2026-11-02)

- PRD A26: the interface's own text no longer says MOCK, demo or prototype; badges read "Sample data" and one "Sample data only" notice stays on every page. Frontend only, 38 files, no API, backend or dependency change.
- Checks: 588 frontend tests pass; tsc and eslint clean. A real-browser scan at 375 px and 1280 px of the home, trip form (with results), My Trips, About, voice and the conversation planning screens found no mock, demo or prototype wording in the interface's own text, tooltips or ARIA labels, with no overflow and no axe violations. The scan first showed my own check was wrong (the example-trip button was misnamed, and one page leaked state into the next), and was fixed and rerun.
- **Still visible, by scope:** backend-supplied fixture text (names such as "Demo Air" and "Demo City Inn", ids such as DEMO-F101, "mock-weather", "(mock)" in weather summaries, "(demo)" in cabin names, and a "Mock fixture text" cancellation line). They arrive from the fixtures and need a backend change to remove.

## 13. Addendum: home screen and fixture wording (2026-11-02)

- PRD A27: three sentences removed from the home screen; the backend fixtures renamed so the visible data no longer says demo or mock (section 12 listed these as out of scope, and the owner then asked for them). The booking simulation panel now reads "SIMULATION ONLY" and "booking simulation".
- Checks: backend 2289 passed and 70 skipped (the PostgreSQL ones run only in CI); ruff, format and mypy clean from `backend/`. Frontend 589 passed; tsc, eslint and build clean. The exported fixture JSON and `docs/openapi.json` were regenerated, so the drift tests pass. A real-browser scan at 375 px and 1280 px found no mock, demo or prototype wording in the visible text on the home, My Trips, About, trip form, planning and voice screens, with no overflow and no axe violations; the home screen had none of the three sentences and the other pages kept the notice. The booking simulation panel strings were reworded after that scan and covered by the unit tests, not by another browser run.
- Not changed: the `MOCK` provenance value everywhere in code, API, database and tests. A few non-visible identifiers keep their names (for example `mock-hotel-goa-resort`, `demo-train-1`, file and component names such as `DemoBanner`).
