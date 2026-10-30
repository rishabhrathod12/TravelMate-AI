# TravelMate AI — Architecture

Status: Draft v0.1 (Milestone 0). Stack decisions are recorded in `docs/ADR/0001-approved-stack.md`.
Requirements referenced below (FR-, NFR-, AC-) are defined in `docs/PRD.md`.

## 1. System overview

TravelMate AI is a web application with a Python backend and a React frontend. The backend exposes a REST API. Behind the API, a planning workflow runs as a LangGraph graph. The graph calls research tools through provider adapters, produces an itinerary and a cost estimate, and pauses for human input at defined points. Trips, runs, quotes and approvals are persisted in PostgreSQL.

```
 Browser (React + TypeScript + Vite)
        │  HTTPS / JSON
        ▼
 FastAPI API layer ──► Trip service ──► Persistence (SQLAlchemy 2.x, PostgreSQL)
        │                    │
        │                    ▼
        │             Planning workflow (LangGraph)
        │              │        │          │
        │              ▼        ▼          ▼
        │        Research   Itinerary   Cost estimator
        │        tools      drafter     (deterministic code)
        │          │          │
        │          ▼          ▼
        │   Provider adapters   LLMClient ──► OpenAI adapter
        │   (mock | live)
        │
        └──► Booking intent & approval service ──► Booking executor
                                                  (disabled in MVP)
```

## 2. Component responsibilities

| Component | Responsibility | Must not |
|---|---|---|
| **API layer** (FastAPI) | Request validation, authentication (see SECURITY §2), routing, error mapping, response provenance fields. | Contain business logic or call providers directly. |
| **Trip service** | Creates and updates trips, starts planning runs, records selections. | Call LLM or provider code directly. |
| **Planning workflow** (LangGraph) | Orchestrates the steps of a planning run, holds run state, and pauses for clarification or selection. | Invoke booking code. |
| **Research tools** | Typed functions that query transport, hotel and weather providers through the provider interfaces and return normalised, provenance-labelled results. | Hold credentials in their return values or write to the database. |
| **Provider adapters** | Implement one interface per data category, in MOCK and LIVE variants. Handle timeouts, retries, and response validation. | Decide what the user sees. |
| **Itinerary drafter** | Uses the LLM through `LLMClient` to turn selected options into a day-by-day draft. | Compute prices or availability. |
| **Cost estimator** | Deterministic arithmetic over quoted and estimated amounts, using integer minor units. | Use LLM output for any figure. |
| **LLMClient** | Protocol for LLM calls: `complete` and `structured_complete`, with a token budget and a timeout. OpenAI adapter is the first implementation. | Be imported by domain code directly. |
| **Booking intent & approval service** | Records booking intents, approvals, and quote snapshots. Enforces the lifecycle in §6. | Be callable from the planning workflow. |
| **Booking executor** | Would perform provider booking calls. **Not implemented in the MVP.** Present only as a disabled interface. | Run unless `BOOKING_ENABLED=true` and an approved intent exists. |
| **Audit log** | Append-only record of significant events (see SECURITY §8). | Be updated or deleted by application code. |
| **Config** | Typed settings loaded from environment variables (Pydantic settings). | Read `.env` values in tests unless a test explicitly sets them. |

## 3. Proposed repository structure

```
TravelMate AI/
├── CLAUDE.md                     # Permanent working rules for Claude Code
├── README.md
├── docker-compose.yml            # Local PostgreSQL only in M1 (app services may be added later)
├── .env.example                  # Variable names and safe placeholders only
├── .gitattributes                # Line-ending normalisation
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── ADR/
│       └── 0001-approved-stack.md
├── backend/
│   ├── pyproject.toml            # Python 3.12, dependency pins, tool config
│   ├── alembic.ini
│   ├── migrations/               # Alembic revisions
│   ├── app/
│   │   ├── main.py               # FastAPI application factory
│   │   ├── config.py             # Pydantic settings
│   │   ├── api/                  # Routers and request/response schemas
│   │   ├── domain/               # Entities, value objects, money, enums (no I/O)
│   │   ├── services/             # Trip, approval and booking-intent services
│   │   ├── workflow/             # LangGraph graph, state, nodes
│   │   ├── tools/                # Research tools exposed to the workflow
│   │   ├── providers/            # Provider interfaces; mock/ and live/ implementations
│   │   ├── llm/                  # LLMClient protocol; openai/ adapter; fakes for tests
│   │   ├── persistence/          # SQLAlchemy models, repositories, session handling
│   │   ├── booking/              # Booking executor interface (disabled)
│   │   └── observability/        # Logging, request IDs, redaction
│   └── tests/
│       ├── unit/
│       ├── architecture/         # Dependency-rule tests (import checks)
│       ├── integration/          # Requires PostgreSQL via Docker Compose
│       ├── contract/             # Provider adapters against recorded fixtures
│       └── fixtures/             # Deterministic mock data (labelled MOCK)
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── api/                  # Typed API client generated or hand-written from schemas
        ├── features/planning/    # Trip request, comparison, itinerary, cost views
        ├── components/           # Provenance badge, mock banner, shared UI
        └── tests/                # Vitest unit tests; Playwright end-to-end tests
```

Dependency rules:
- `domain/` imports nothing from the rest of `app/`.
- `workflow/` and `tools/` depend on interfaces in `providers/` and `llm/`, never on concrete live adapters.
- `booking/` is imported only by `services/` (approval path). The `workflow/` package must not import `booking/`. A test enforces this (see §10).
- Concrete adapters are selected in one place, the composition root in `main.py`.

## 4. Agent responsibilities and tool boundaries

The planner is a small set of cooperating steps in one LangGraph graph. Each step is a node with a narrow job. Agents are not free-roaming.

| Node | Responsibility | Tools it may call | Output |
|---|---|---|---|
| `intake` | Validate the trip request, identify missing fields, produce clarification questions. | None (schema validation and LLM extraction only). | Validated `TripRequest` or clarification request. |
| `research` | Run transport, hotel and weather research in parallel. | `search_transport`, `search_hotels`, `get_weather` (read-only). | Provenance-labelled option lists and per-provider errors. |
| `select` (human) | Pause for the user to choose options. | None. | Selected option IDs. |
| `itinerary` | Draft the day-by-day plan from selections and weather. | None beyond `LLMClient`. | Itinerary draft with source references to options. |
| `cost` | Compute the estimate. | None (deterministic code). | `CostEstimate` with line items and provenance. |
| `summarise` | Assemble the response and persist results. | Persistence writes for the trip and run only. | Trip summary. |

Tool boundary rules:
1. **No LLM-facing tool can create, modify or confirm a booking.** The booking service is not registered as a tool with any agent.
2. Research tools are read-only with respect to external systems.
3. Each tool validates its inputs against a schema and returns a typed result, not free text.
4. Tool results are treated as untrusted data (SECURITY §3).
5. The LLM never produces prices, availability, or dates that are presented as provider facts. It may describe or reorder data that came from tools.
6. Tool calls are capped per run (NFR-09) and each call is recorded with its provider, latency, and outcome.

## 5. Data model

Money is stored as `amount_minor BIGINT` plus `currency CHAR(3)`. Timestamps are `TIMESTAMPTZ` in UTC. Every provider-derived record stores `provenance`, `provider_name`, `retrieved_at` and `freshness_window_seconds`.

| Table | Purpose | Key fields |
|---|---|---|
| `trips` | Trip container and owner. | `id`, `owner_id` (nullable until Q4 is resolved), `title`, `status`, timestamps. |
| `trip_requests` | Validated input, versioned per run. | `id`, `trip_id`, origin, destination, `trip_type`, `departure_date`, `return_date` (null for one-way), travellers, budget. |
| `agent_runs` | One planning execution. | `id`, `trip_id`, `status`, `checkpoint_ref`, `llm_calls`, `provider_calls`, timestamps. |
| `provider_calls` | Each external call. | `id`, `run_id`, `category`, `provider_name`, `mode` (MOCK/LIVE), `status`, `latency_ms`, `error_code`. |
| `options` | Research results. | `id`, `run_id`, `category`, `payload` (JSONB), `provenance`, `retrieved_at`. |
| `quotes` | Price snapshot for a specific option at a time. | `id`, `option_id`, `amount_minor`, `currency`, `valid_until`, `content_hash`. |
| `itineraries` | Itinerary versions. | `id`, `trip_id`, `version`, `content` (JSONB), `created_by` (`agent` or user). |
| `cost_estimates` | Estimate and breakdown. | `id`, `run_id`, `total_minor`, `currency`, `breakdown` (JSONB with provenance per line). |
| `booking_intents` | Requested bookings. | `id`, `trip_id`, `quote_id`, `status`, `idempotency_key` (UNIQUE), `created_at`. |
| `approvals` | Human approvals. | `id`, `booking_intent_id`, `approver_id`, `quote_content_hash`, `approved_at`, `expires_at`. |
| `audit_events` | Append-only log. | `id`, `occurred_at`, `actor`, `event_type`, `entity_type`, `entity_id`, `data` (redacted JSONB). |

**Status (M9, 2026-10-30):** all eleven tables exist as SQLAlchemy models (`app/persistence/models.py`) and as one reviewed Alembic revision (`backend/migrations/versions/0001_initial_schema.py`). Differences from the table above, all deliberate:
- `trips.draft` holds the request as the traveller gave it, which may be incomplete; the validated request is `trip_requests`, one row per run. `trips.owner_id` is not nullable.
- `agent_runs` also holds `owner_id`, `run_number` (unique within a trip) and the whole `outcome` as JSON, so a run can be read back after a restart; `options` and `cost_estimates` hold queryable copies of the same data.
- `itineraries.version` is unique within a trip.
- `audit_events.request_id` is added because SECURITY section 8 requires it.
- `provider_calls` exists, but nothing writes it yet (M12).
- M10 (revision `0002`) reshaped `quotes`, `booking_intents` and `approvals`, which had never held a row: a quote stores the whole snapshot, its trip and its content hash; an intent stores its owner, a hash of the caller's idempotency key, a hash of what was asked for and `updated_at`; an approval names the quote snapshot it approved. Quotes and approvals are append-only for the application role, and an intent may be updated but not deleted.

Migrations are managed with Alembic. Each schema change is a reviewed revision with a working downgrade or a documented reason why none exists.

## 6. Human approval and booking lifecycle

Booking is a separate lifecycle from planning. Planning can run without any booking state.

```
DRAFT ──► QUOTED ──► AWAITING_APPROVAL ──► APPROVED ──► REVALIDATION ──► BOOKING ──► CONFIRMED
                          ▲                                  │               │
                          └──── quote changed or invalid ────┘               ▼
                                                                          FAILED

CANCELLED / EXPIRED: reachable from any state before CONFIRMED
```

| State | Meaning | Entry condition |
|---|---|---|
| DRAFT | Intent recorded, no price check yet. | User selects an option and requests a booking intent. |
| QUOTED | A quote snapshot is stored with a `valid_until`. | Provider quote retrieved (LIVE) or mock quote generated (MOCK). |
| AWAITING_APPROVAL | A human must approve this exact quote. | Quote stored and displayed. |
| APPROVED | Approval recorded with `quote_content_hash`. | Human approves the displayed quote. |
| REVALIDATION | Quote is re-checked immediately before execution. | Approved intent is about to be executed. |
| BOOKING | Execution in progress. | Revalidation passed and `BOOKING_ENABLED=true`. |
| CONFIRMED | Provider confirmed the booking. Stores the provider reference. | Provider response validated. |
| FAILED | Execution failed. No retry without a new approval. | Provider error or validation failure. |
| NEEDS_REVIEW | Execution outcome is unknown (for example, a timeout after the booking request was sent). Blocks further action until a human checks the provider. | Ambiguous provider outcome. |
| CANCELLED / EXPIRED | Terminal, no further action. | User cancels, or `valid_until` passes before approval. |

Rules:
- **MVP behaviour:** the service can reach DRAFT → QUOTED → AWAITING_APPROVAL → APPROVED and records the approval. Transitions to BOOKING and beyond are not implemented. The API returns a clear "booking disabled" status instead of a booking outcome.
- An approval is valid only for the `quote_content_hash` it was given for. Any change in price, currency, availability or option details invalidates it and returns the intent to AWAITING_APPROVAL.
- Execution requires the approval to be unexpired (Q7).
- Every transition writes an audit event.
- A booking is never reported as CONFIRMED unless a provider response confirming it has been received and validated.

## 7. API design

Base path `/api/v1`. JSON only. Every response includes `request_id`. Monetary values are objects `{ "amount_minor": int, "currency": "INR" }`. Every provider-derived value includes `provenance`.

| Method | Path | Purpose | MVP |
|---|---|---|---|
| POST | `/trips` | Create a trip from a request. | Yes |
| GET | `/trips/{trip_id}` | Get a trip with its latest run and selections. | Yes |
| POST | `/trips/{trip_id}/runs` | Start a planning run. Returns `202` and a run ID. | Yes |
| GET | `/runs/{run_id}` | Run status, clarification questions, options, errors. | Yes |
| POST | `/runs/{run_id}/clarifications` | Answer clarification questions and resume. | Yes |
| POST | `/runs/{run_id}/selections` | Choose transport and hotel options and resume. | Yes |
| GET | `/trips/{trip_id}/itinerary` | Latest itinerary. | Yes |
| POST | `/trips/{trip_id}/itinerary/versions` | Save a user-edited itinerary as a new version. | Yes |
| GET | `/runs/{run_id}/cost-estimate` | Cost estimate with breakdown. | Yes |
| POST | `/trips/{trip_id}/booking-intents` | Create a booking intent for a quote. | Yes (records only) |
| POST | `/booking-intents/{intent_id}/approvals` | Record human approval for the displayed quote. | Yes (records only) |
| POST | `/booking-intents/{intent_id}/execute` | Execute booking. | Returns `409 booking_disabled` in MVP |

Error format follows RFC 9457 (Problem Details). Validation errors use `422`. Provider failures inside a run are reported in the run's `errors` list with `200`, not as HTTP failures, because the run is partially successful (AC-04).

**Status (M10, 2026-10-30):** every route above is implemented. Planning records are durable when `DATABASE_URL` is set (M9) and the caller is the one configured development principal until PRD Q4 is resolved. Responses for intents carry `booking_enabled: false` and a plain notice, and error bodies for booking carry a stable `code` (`quote_mismatch`, `quote_changed`, `quote_expired`, `revalidation_failed`, `idempotency_conflict`, `booking_disabled`, and so on). `POST .../booking-intents` answers `201` for a new intent and `200` when the same key and request repeat. There is no payment route.

Long-running planning uses `202` and polling in the MVP. Server-sent events are a later option, not a requirement.

## 8. Workflow design

- The graph state is typed (Pydantic model). Each node returns a partial update.
- Human pauses use LangGraph interrupts. The run is persisted with a checkpoint, so it survives a process restart. The checkpointer uses PostgreSQL.
- Research nodes run in parallel. Each provider call has its own timeout. A failed call adds an entry to `errors` and does not stop other branches.
- The graph has a maximum step count and a maximum number of tool calls per run (NFR-09). Exceeding either ends the run in an explicit `stopped_limit` status.
- Resuming a run requires the run's owner (SECURITY §2) and a valid checkpoint.
- Deterministic nodes (`cost`, validation) are plain functions with unit tests. The LLM is used only where language understanding or drafting is required.

## 9. Error handling, retries and timeouts

| Concern | Decision |
|---|---|
| Provider timeout | 5 s for search and weather; 10 s for quote retrieval. Configurable per provider. |
| Retries | Up to 2 retries with exponential backoff and jitter, for idempotent reads only, and only for timeouts, 429 and 5xx responses. |
| Booking calls | Never retried automatically. An ambiguous outcome (for example, a timeout after the request was sent) moves the intent to a state that needs human review. Any retry needs a new revalidation and, where the provider supports it, the same idempotency key (SECURITY §6). |
| Provider response validation | Responses are parsed into typed models. Invalid responses are rejected as `ProviderInvalidResponse` and never partially used. |
| LLM errors | Timeouts and rate limits retry once. Invalid structured output triggers one repair attempt, then the step fails with a clear error. |
| Partial results | Allowed and labelled. The response lists which categories are missing and why. |
| Unknown exceptions | Logged with a request ID and returned as a generic `500` problem. Stack traces are not sent to clients. |

Error categories are typed exception classes so tests can assert on them.

## 10. Observability

- **Logs:** structured JSON with `request_id`, `run_id`, `trip_id` where relevant, level, and event name. Sensitive fields are redacted before logging (SECURITY §9).
- **Metrics (planned):** provider call count, latency and error rate by provider and mode; LLM token use and cost per run; run durations and status counts.
- **Tracing:** deferred. The design keeps request and run IDs in a shape that can be mapped to OpenTelemetry later.
- **Audit:** `audit_events` is separate from logs and is retained according to the policy in SECURITY §8.

## 11. Testing strategy

| Layer | Scope | Network | Tooling |
|---|---|---|---|
| Unit | Domain rules, money arithmetic, cost estimator, state transitions, validators | None | pytest |
| Contract | Each provider adapter against recorded fixtures and schema checks | None | pytest, recorded fixtures |
| Workflow | Graph with fake providers and fake LLM, including interrupts and partial failures | None | pytest, LangGraph test utilities |
| Integration | Repositories, migrations, and transactions against PostgreSQL | Local Docker only | pytest, Docker Compose |
| API | Endpoints end to end in mock mode, including AC-05 spy test | None | pytest with the FastAPI test client |
| Architecture | Dependency rules in §3 (for example, `workflow` must not import `booking`) | None | pytest with an import-graph check |
| Frontend unit | Components and API client | None | Vitest |
| Frontend end to end | Planning flow at desktop and 375 px widths | Local servers | Playwright |
| Security | Secret scan, dependency audit, log-redaction test | None | CI scripts (tooling chosen in Milestone 1) |

Rules:
- CI runs without real API keys and without outbound network access to providers or the LLM.
- Live-provider tests, when they exist, are opt-in, marked, and excluded from default runs.
- Fixtures are deterministic. A test that depends on the current date sets the date explicitly.
- The Indore to Goa scenario is the primary acceptance fixture (AC-01).

## 12. Deferred decisions and extension points

- **Redis and Celery:** added only when a requirement needs background work with retries that outlive a request, for example scheduled price tracking.
- **Live providers:** each category has an interface, so a live adapter can be added without changing the workflow.
- **Authentication provider:** unresolved (PRD Q4). The API layer has a single authentication dependency so the mechanism can change without touching routes.
- **Payments:** not designed in the MVP (PRD Q8).
