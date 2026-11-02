# TravelMate AI: MVP acceptance record (Milestone 12)

Status: **Draft, awaiting owner review.** Run on 2026-11-02 against commit `d21d1ce` plus the uncommitted M12 changes listed at the end. Plan: `docs/IMPLEMENTATION_PLAN.md` M12. Requirements: `docs/PRD.md` §8 and §9.

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
