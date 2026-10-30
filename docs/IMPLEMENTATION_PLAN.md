# TravelMate AI — Implementation Plan

Status: Draft v0.1. Milestone 0 is complete when this document and the other foundation documents are reviewed.

Each milestone is done only when its completion criteria are met and its verification steps have been run with the actual results recorded. Milestones are sequential unless a dependency allows parallel work. Stop for review at the end of each milestone.

## Dependency overview

```
M0 Docs & conventions
 └─► M1 Repository foundation & local environment
      └─► M2 Domain model & money/time rules
           └─► M3 Provider interfaces & mock providers
           │    └─► M4 Research tools & option comparison
           │         └─► M5 Cost estimator
           │              └─► M6 Itinerary drafter (LLM interface)
           │                   └─► M7 Planning workflow (LangGraph)
           │                        └─► M8 API layer
           └─► M9 Persistence (PostgreSQL, SQLAlchemy, Alembic)
                └─► M7 (checkpointing) and M8 (storage)
M8 + M9 ─► M10 Booking intents & approvals (booking disabled)
M8 ─► M11 Frontend planning flow
M10 + M11 ─► M12 Hardening, security checks and MVP acceptance
M12 ─► M13 Live provider integration (requires authorization, PRD Q1–Q3)
M13 ─► M14 Booking execution (requires authorization, ADR, and review)
```

Parallel work is possible after M8 for M10 and M11, and after M3 for M9.

---

## M0 — Project documentation and engineering conventions

Goal: agreed product, architecture, security and working rules before code.

Deliverables:
- `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/IMPLEMENTATION_PLAN.md`
- `CLAUDE.md`
- `docs/ADR/0001-approved-stack.md`
- `.gitignore` (Python, env, IDE, cache rules) and `.gitattributes`

Completion criteria:
- All deliverables exist and are non-empty.
- Documents agree on terms (provenance labels, booking states, component names, section references).
- Open questions are listed with owners and the milestones they block.
- No application code, tests or dependency changes.

Verification:
- Read each file back and check for broken section references (for example, SECURITY §8 is audit logs).
- `git status` shows only documentation and configuration files.
- `git ls-files --eol` confirms no unintended line-ending changes.

Blocked by: nothing. Blocks: M1.

---

## M1 — Repository foundation and local environment

Goal: an empty but runnable project that every later milestone builds on.

Deliverables:
- `backend/pyproject.toml` pinning Python 3.12 (`requires-python = ">=3.12,<3.13"`) and the approved libraries.
- `backend/app/` skeleton with `main.py` (FastAPI app factory returning a health endpoint) and `config.py` (Pydantic settings, no secrets in code).
- `backend/tests/` with one passing smoke test.
- `.env.example` with variable names and placeholders only.
- `docker-compose.yml` with a PostgreSQL service only.
- `frontend/` scaffold with Vite, React and TypeScript, running a placeholder page.
- Lint, type check and test commands defined in one place (for example, a `Makefile` or task runner documented in `README.md`).
- CI workflow that runs lint, type check, backend tests and frontend tests with no secrets.
- Secret scanning and dependency audit steps in CI (SECURITY §10).

Completion criteria:
- Backend health endpoint responds and its test passes.
- Frontend builds and its test passes.
- PostgreSQL starts from Docker Compose and accepts connections. **Deferred and unverified.** Docker is not available on the development machine, and nothing in M1 uses the database. No PostgreSQL test has been run. Verify when Docker is available and the database is first needed (M9).
- Settings refuse to start in production mode without required secrets (SECURITY §1). **Not implemented and not waived.** M1 defines no required secret, so there is nothing to check yet. The full production startup validation is planned for M9, which introduces the first required secret (`DATABASE_URL`). Until then this criterion stays open, and the baseline below applies.
- A Python 3.12 environment is used: `backend/.venv`. The old 3.14 `aitravel/` venv was rebuilt on 3.12.10 on 2026-10-29 and may be used as a fallback; it must not be 3.14.

Verification:
```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e backend[dev]
backend\.venv\Scripts\python.exe -m pytest backend\tests
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\app
cd frontend; npm ci; npm run build; npm test
docker compose up -d db
docker compose ps
```

Secret-handling baseline that applies from M1 (SECURITY §1):
- Enforced now:
  - `.env` and `.env.*` are gitignored, and `.env.example` is kept. Real credentials are never committed.
  - No API keys are hard-coded. `app/config.py` reads the process environment only and defines no secret yet. A test asserts it does not read an env file.
  - `.env.example` holds names and obvious placeholders only. A test checks that secret-like variables are empty or placeholders.
  - The health endpoint does not need `DATABASE_URL` or LLM credentials. A test runs it with both unset.
  - The code has no logging of settings or secrets. This holds because no logging code exists yet, not because redaction is built.
- Not implemented yet (planned, not claimed):
  - Masking of secrets in the settings `repr` (SECURITY §1): when the first secret is added, M9.
  - Production startup validation of required secrets: M9.
  - Redacted structured logging and the secret-redaction test (AC-08): M8.
- Configured but not yet run: the gitleaks secret scan and the dependency audits in CI. They have run locally for `pip-audit` and `npm audit` only.

Blocked by: M0. Blocks: M2.

Note: installing dependencies is a separate approval step. This milestone's first implementation task will ask for it.

---

## M2 — Domain model and money/time rules

Goal: the core types everything else uses, with no I/O.

Deliverables:
- Entities and value objects: `TripRequest` (with `TripType`, `departure_date` and an optional `return_date`), `Location`, `Traveller`, `Money`, `Provenance`, `Option` (transport, hotel, weather base types), `Quote`, `CostEstimate`, `CostLine`, `Itinerary`, `BookingIntent`, `Approval`.
- `Money` as integer minor units plus ISO 4217 currency, with addition, comparison and currency-mismatch errors.
- Enums: `Provenance` (LIVE, CACHED_LIVE, MOCK), `BookingStatus` (the states in ARCHITECTURE §6), `RunStatus`.
- UTC time handling and a destination time-zone helper.
- Validation rules for trip requests: one-way, round-trip and same-day return trips are supported. A one-way trip has no return date; a round trip needs a return date on or after the departure date. The traveller count range is an open decision (PRD §11, Q14).

Completion criteria:
- Unit tests cover money arithmetic, currency mismatch, state transition table (valid and invalid transitions), and request validation.
- No module in `domain/` imports from other `app/` packages (architecture test).

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit -q
backend\.venv\Scripts\python.exe -m pytest backend\tests\architecture -q
```

Blocked by: M1. Blocks: M3, M9.

---

## M3 — Provider interfaces and mock providers

Goal: every external data category has an interface and a deterministic mock, so the system runs end to end with no network.

Deliverables:
- Interfaces: `TransportProvider`, `HotelProvider`, `WeatherProvider`, each with a search or get method that returns typed results or raises a typed error.
- Typed error classes: `ProviderUnavailable`, `ProviderRateLimited`, `ProviderInvalidResponse`, `ProviderTimeout`.
- Mock implementations that load deterministic fixtures and label every result `MOCK`.
- Fixture set for the Indore to Goa scenario, clearly named as mock data.
- Provider selection by configuration (`PROVIDER_MODE_*`), with a startup check.
- Timeouts and bounded retries for idempotent reads (ARCHITECTURE §9).

Completion criteria:
- Mock providers return the same typed shape as the interfaces, with `provenance=MOCK`.
- Contract tests pass for each mock.
- A failing fake provider produces the typed error, and retries are bounded (tested with a counter).
- No LIVE adapter is implemented in this milestone.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\contract backend\tests\unit -q
```

Blocked by: M2. Blocks: M4, M9.

---

## M4 — Research tools and option comparison

Goal: typed research tools that the workflow can call, plus comparison logic.

Deliverables:
- Tools `search_transport`, `search_hotels`, `get_weather` wrapping the provider interfaces, with input and output schemas.
- Per-call recording (provider name, mode, latency, status) in an in-memory recorder for now.
- Comparison function that sorts and groups options by price, duration, stops, rating and cancellation terms, and shows which fields are missing.
- Partial-failure handling: a failing provider adds an error entry and does not raise.

Completion criteria:
- AC-04 (partial result on provider failure) passes.
- AC-02 provenance check passes for every tool output.
- Tools reject invalid inputs with a validation error and do not call providers.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit backend\tests\contract -q
```

Blocked by: M3. Blocks: M5, M7.

---

## M5 — Cost estimator

Goal: deterministic trip cost estimate with a breakdown and provenance.

Deliverables:
- Estimator with line items: transport, accommodation (per night, per room), local transport allowance, contingency percentage, optional taxes or fees supplied by providers.
- Budget comparison (under, within, over budget).
- Provenance for each line and for the total (lowest of the inputs).
- Rules for missing inputs: the estimate is produced with an explicit "incomplete" flag and the missing items listed. It is never silently zero.

Completion criteria:
- AC-03 passes: total equals the sum of lines in integer minor units, including rounding rules tested.
- Total provenance is MOCK if any input is MOCK.
- No LLM is used in this module.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit -k cost -q
```

Blocked by: M4. Blocks: M7.

---

## M6 — Itinerary drafter and LLM interface

Goal: LLM-assisted itinerary drafting behind a replaceable interface, with strict validation.

Deliverables:
- `LLMClient` protocol with `complete` and `structured_complete`, timeouts and token limits.
- OpenAI adapter implementing the protocol, reading the key from settings only.
- `FakeLLMClient` for tests, returning scripted responses and recording calls.
- Itinerary drafter that takes selected options and weather as delimited data, returns a typed `Itinerary`, and rejects references to unknown option IDs (SECURITY §3).
- Prompt-injection test cases in hotel names, reviews and notes (SECURITY §3, item 9).
- One repair attempt on invalid structured output, then a clear failure.

Completion criteria:
- All tests use `FakeLLMClient`. No test calls the OpenAI API.
- A test confirms the adapter fails fast when no key is configured.
- Injection test cases do not change booking state or call any tool outside the allowed set.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit -k "llm or itinerary" -q
```

Blocked by: M5. Blocks: M7.

Open dependency: the first live LLM call needs an owner-supplied key and a separate explicit approval, and is not part of this milestone's verification.

---

## M7 — Planning workflow (LangGraph)

Goal: the full planning run as a resumable graph with human pauses.

Deliverables:
- Graph state model and nodes from ARCHITECTURE §4: `intake`, `research`, `select`, `itinerary`, `cost`, `summarise`.
- Clarification interrupt in `intake` and selection interrupt in `select`.
- PostgreSQL-backed checkpointer (depends on M9 for the database; tests use an in-memory checkpointer first).
- Step and tool-call limits with a `stopped_limit` status.
- Run recording of LLM calls and provider calls.

Completion criteria:
- AC-01 passes in mock mode end to end at the workflow level.
- AC-09 passes: missing inputs cause clarification and no provider calls.
- A run resumes correctly after an interrupt, verified in tests.
- The architecture test confirms `workflow/` does not import `booking/`.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit backend\tests\integration -k workflow -q
```

Blocked by: M4, M5, M6, M9 (checkpointer only). Blocks: M8.

---

## M8 — API layer

Goal: the REST API described in ARCHITECTURE §7.

Deliverables:
- FastAPI routers for trips, runs, clarifications, selections, itinerary, cost estimate.
- Pydantic request and response schemas, with provenance and money objects.
- Problem Details error responses (RFC 9457).
- Authentication dependency (SECURITY §2). The mechanism follows PRD Q4. Until Q4 is resolved, the local development principal is explicit configuration, not a default.
- Request ID middleware and redacted structured logging (SECURITY §9).
- Planning runs return `202` and are polled.

Completion criteria:
- API tests for every endpoint in mock mode.
- AC-08 passes: secret-redaction test.
- Ownership checks: a principal cannot read another owner's trip (test).
- The OpenAPI schema is generated and committed as a reviewed artifact.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit backend\tests\integration -k api -q
```

Blocked by: M7, M9. Blocks: M10, M11.

---

## M9 — Persistence

Goal: durable storage for trips, runs, options, quotes, itineraries, estimates, intents, approvals and audit events.

Deliverables:
- SQLAlchemy 2.x models matching ARCHITECTURE §5, with repositories and transaction handling.
- Alembic migrations, with the initial revision reviewed.
- Application database role that cannot `UPDATE` or `DELETE` `audit_events` (SECURITY §8), created by a migration.
- Unique constraint on `booking_intents.idempotency_key`.
- Integration tests using the Docker Compose PostgreSQL service.

Completion criteria:
- Migrations apply from empty and downgrade cleanly, or a documented reason is recorded for any downgrade that cannot.
- Integration tests pass against PostgreSQL.
- Permission test confirms `UPDATE` and `DELETE` on `audit_events` are denied for the application role.

Verification:
```powershell
docker compose up -d db
backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
backend\.venv\Scripts\python.exe -m pytest backend\tests\integration -k persistence -q
backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini downgrade base
```

Blocked by: M1, M2. Blocks: M7 (checkpointer), M8, M10.

---

## M10 — Booking intents and approvals (booking disabled)

Goal: the human approval path is built and tested, while no booking can execute.

Deliverables:
- Services that create booking intents, store quote snapshots with `valid_until`, compute `quote_content_hash`, and record approvals (ARCHITECTURE §6).
- Booking executor interface with a `DisabledBookingExecutor` that always returns a "booking disabled" result.
- Endpoints from ARCHITECTURE §7 for intents and approvals. The execute endpoint returns `409 booking_disabled`.
- Expiry logic for quotes and approvals (PRD Q7 default if not yet confirmed).
- Audit events for every transition (SECURITY §8).

Completion criteria:
- AC-05 passes: spy on the booking client; `BOOKING_ENABLED=false` records intent and never calls it.
- AC-06 passes: approval for an expired or changed quote is rejected. (Tested with the mock revalidation path.)
- Duplicate intent requests with the same idempotency key return the existing intent.
- Startup refuses to run with `BOOKING_ENABLED=true` (SECURITY §1), until M14 is approved.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -k "booking or approval" -q
```

Blocked by: M8, M9. Blocks: M12.

---

## M11 — Frontend planning flow

Goal: the user can plan the Indore to Goa trip in the browser and see provenance clearly.

Deliverables:
- Trip request form with validation and clarification prompts.
- Run progress and results view: transport and hotel comparison, weather, errors per provider.
- Provenance badge on every price and availability value, and a persistent banner when any MOCK data is used (PRD §9).
- Itinerary view with edit and save-as-new-version.
- Cost estimate view with itemised breakdown.
- Booking intent view with approval panel showing full total, terms and the statement that approval attempts a real booking. In MVP the execute action is shown as disabled with its reason.
- Responsive layout that works at 375 px without horizontal scrolling (AC-10).

Completion criteria:
- Vitest unit tests for components and the API client.
- Playwright tests for the full mock-mode flow at desktop and 375 px widths.
- Accessibility check on core screens (NFR-12 target).

Verification:
```powershell
cd frontend
npm test
npx playwright test
```

Blocked by: M8 (API contract). Can start in parallel with M10 once the API schema is committed.

---

## M12 — Hardening and MVP acceptance

Goal: confirm the MVP meets the PRD and the security requirements before anyone relies on it.

Deliverables:
- Full acceptance run against AC-01 to AC-10, with results recorded.
- Prompt-injection test suite complete (SECURITY §3).
- Log-redaction and secret-scan results (SECURITY §9, §1).
- Dependency audit results, with any findings either fixed or accepted in writing.
- Performance check against NFR-07 (mock plan under 10 s).
- Known-limitations list for the MVP release.
- CI hardening (deferred from M1): pin the GitHub Actions in `.github/workflows/ci.yml` to full commit SHAs, and review the gitleaks licence terms if the repository moves to an organisation.

Completion criteria:
- Every AC passes, or the failing item is documented and approved by the owner.
- No open high-severity security findings.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend; npm test; npx playwright test
```

Blocked by: M10, M11. Blocks: M13.

---

## M13 — Live provider integration (requires authorization)

Goal: replace MOCK adapters with authorized live providers, one category at a time.

Preconditions:
- PRD Q1–Q3 resolved: provider selected, terms reviewed, credentials obtained by the owner.
- Freshness windows set (PRD Q6).
- An ADR recording the provider choice.

Deliverables (per category):
- LIVE adapter implementing the existing interface.
- Recorded fixtures from the provider's documented sandbox, if one exists, or from a reviewed sample. Fixtures contain no personal data.
- Provenance set to LIVE or CACHED_LIVE with `retrieved_at` and freshness window.
- Live-tagged tests, opt-in and excluded from CI.

Completion criteria:
- Contract tests pass against recorded fixtures.
- Opt-in live smoke test passes when run manually by the owner, with results recorded.
- Mock and live modes can be mixed per category, and the UI shows the mix.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\contract -q
backend\.venv\Scripts\python.exe -m pytest -m live -q   # manual, owner-run only
```

Blocked by: M12 and external authorization. Blocks: M14.

---

## M14 — Booking execution (requires authorization and review)

Goal: allow a real booking only after an approved, revalidated, idempotent path exists.

Preconditions:
- M13 complete for the relevant category.
- Provider's booking API terms reviewed and an ADR recorded.
- PRD Q7 and Q8 resolved (approval expiry, payment model if applicable). Payments remain out of scope unless separately approved.
- Security review of the executor (SECURITY §4 and §6).

Deliverables:
- Booking executor for the approved provider, implementing the lifecycle in ARCHITECTURE §6, including REVALIDATION and ambiguous-outcome handling.
- Idempotency keys sent to the provider where supported.
- Tests with fakes for every transition, including timeout after send (must go to review, not retry).
- Enablement change reviewed, with `BOOKING_ENABLED` documented per environment.

Completion criteria:
- AC-06 passes for the live revalidation path.
- Duplicate-booking tests pass under concurrent requests (SECURITY §6).
- Owner has explicitly authorized enablement in writing, recorded in the project.

Verification:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -k "booking" -q
backend\.venv\Scripts\python.exe -m pytest -m live -q   # manual, owner-run only, after authorization
```

Blocked by: M13 and authorization. Nothing depends on it.

---

## Milestone status

| Milestone | Status |
|---|---|
| M0 Docs & conventions | Complete (committed and pushed as d0b929d) |
| M1 Foundation | Implemented, awaiting owner review. Backend, frontend scaffold, Docker Compose file and CI workflow exist. **Open criteria:** (1) PostgreSQL start from Docker Compose is deferred and unverified (no Docker available); (2) the production-secrets startup guard is not implemented and is planned for M9. CI has run: all three jobs (backend, frontend, secret-scan) passed for the M1 commit 0204410 (GitHub Actions run 40890476155; job status read, logs not read) |
| M2 Domain model | Implemented except `budget` on `TripRequest` (the weather type was added during M3); awaiting owner review. Done and unit-tested: `TripRequest`, `Money`, UTC and time-zone helpers, `SourceMetadata`, transport and hotel options, `Quote`, cost types, `Itinerary`, the `BookingStatus` transition table (17 allowed edges, all other pairs rejected), `BookingIntent`, `Approval`, `RunStatus`, and the domain import-rule test. Several choices are provisional and several transitions are deliberately rejected pending owner decisions (PRD §10 A5–A9, §11 Q9–Q16). Not closed |
| M3 Provider interfaces & mocks | Implemented, awaiting owner review; no live adapter. Done and tested: synchronous `TransportProvider`, `HotelProvider` and `WeatherProvider` interfaces with typed queries; the four typed errors; a bounded-retry helper (1 try plus at most 2 retries, counted in tests) with the 5 s default timeout; deterministic MOCK providers for Indore and Goa in both directions that return nothing for other places; `PROVIDER_MODE_*` settings and a startup check that refuses `live`; the weather domain type; contract tests for each mock; architecture tests (providers depend only on the domain, mocks use no network library, only the providers package imports the mocks). Open and deliberately not decided here: price basis (Q12), hotel stay windows and rooms for one-way and same-day trips (Q13, Q14). The bundled fixtures are Python data in `app/providers/mock/`, not files under `tests/fixtures/`. Not closed |
| M4 Research tools | Implemented, awaiting owner review. Done and tested: `search_transport`, `search_hotels` and `get_weather` with input schemas (bad input is rejected and no provider is called); bounded retries; an in-memory recorder with one record per actual provider call (tool, provider, mode, status, latency); a provider failure becomes an error entry and never hides the other categories (AC-04); an empty result always carries a reason; a mock provider's data must be labelled MOCK or it is rejected (AC-02); sorting and grouping with missing values last, `missing_fields`, and read-only tool specs for later LLM tool calling. Ratings are not modelled, and cancellation terms are grouped only by presence. The `Providers` bundle moved from `providers/factory.py` to `providers/base.py` so tools depend on interfaces only. Not closed |
| M5 Cost estimator | Implemented as pure arithmetic over explicit inputs, awaiting owner review. Done and tested: `Money` subtract and whole-number multiply; exact integer percentage in basis points with four explicit rounding modes (checked against an independent fraction reference); `estimate_cost` with an exact sum (AC-03) that lists every required input not supplied instead of treating it as zero; estimate provenance as the weakest line; `compare_to_budget` marking a result provisional when the estimate is incomplete. **Not wired and no defaults:** the quantity behind each line (Q12), which lines do not apply (Q13), and the contingency percentage, base and rounding mode (Q18) must come from the caller (M7). Open: Q16, Q17. Not closed |
| M6 Itinerary & LLM interface | Implemented with fakes only, awaiting owner review; **no live model call has ever been made**. Done and tested: the `LLMClient` protocol (no tools field), a scripted `FakeLLMClient`, typed LLM errors, one retry for a timeout or rate limit, one repair attempt for an unusable answer, a call recorder holding no prompts or answers, and the itinerary drafter. The drafter shows the model only aliases, descriptive text and weather by day number, in a hash-derived data block; it rejects unknown option references and any extra field, and flags text that seems to state a price, time, date or booking claim. A prompt-injection suite covers hostile text in hotel names, weather text, place names and notes (106 tests). The OpenAI adapter fails fast without a key and model and is tested against a fake transport; **its real transport, the `openai` package and the wire format against the live API are not done and not verified.** `OPENAI_API_KEY` is a `SecretStr`, never printed. Open: Q13 (days for one-way and same-day), Q19 (model, limits, key). Not closed |
| M7 Planning workflow | Implemented in memory, awaiting owner review. Done and tested: the typed state and graph (`intake`, parallel `research`, `select`, `itinerary`, `cost`, `summarise`) in `app/workflow/`; a pause for clarification in `intake` and a pause for a choice in `select`, each resumable; step, tool-call and answer limits ending a run as `stopped_limit`; owner checks on every run; AC-01 (full mock run), AC-04 (a failing provider gives a partial result) and AC-09 (missing inputs give questions and no provider calls) pass at workflow level; the architecture test confirms `workflow/` does not import `booking/`. Applies the owner's rules from Q12, Q13 and Q18. **Not done:** the PostgreSQL checkpointer (the in-memory one is used until M9), any API endpoint (M8), any real model call (the itinerary step runs on the fake model in tests), and recording runs anywhere but in memory. Rooms per party is still an explicit input with no default. Not closed |
| M8 API layer | Implemented in memory, awaiting owner review. Done and tested: routers for trips, runs, clarifications, selections, itinerary (and saved versions) and the cost estimate under `/api/v1`; request and response schemas that carry provenance and money objects; Problem Details (RFC 9457) errors on every route; request ids on every response and in every error body; structured JSON logging with redaction (AC-08: a known fake secret appears in no log line and no response, checked also against a running uvicorn); a service layer that compares the owner on every call (a trip or run that is someone else's is "not found"); planning runs that return `202` and are polled, run on a background thread pool; per-run limits and a per-owner hourly run limit; the OpenAPI document generated and committed as `docs/openapi.json`, with a test that fails if it is stale. **Not done:** durable storage (everything is in memory until M9), real authentication (PRD Q4: calls act for one configured development principal and the API refuses to start in production), booking intents, approvals and the `409 booking_disabled` execute endpoint (M10). Not closed |
| M9 Persistence | Not started |
| M10 Booking intents & approvals | Not started |
| M11 Frontend | Prototype only, started ahead of M8 with owner approval. A labelled demo-data interface exists (plan form, option cards, cost estimate, sample itinerary, read-only approval preview); only `GET /health` is real. M11 criteria are not met: no API client for real endpoints, no Playwright tests, no accessibility audit, and the approval and booking views are not connected to anything |
| M12 Hardening & acceptance | Not started |
| M13 Live providers | Blocked on authorization |
| M14 Booking execution | Blocked on authorization and review |
