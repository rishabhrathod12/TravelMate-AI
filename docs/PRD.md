# TravelMate AI — Product Requirements Document

Status: Draft v0.1 (Milestone 0)
Owner: Project owner (to be named)

## 1. Problem statement

Planning a multi-leg trip means checking several transport providers, hotel sites, and weather sources, then turning the results into an itinerary and a budget by hand. The information is scattered, prices change between checking and booking, and it is hard to tell which numbers are current. Travellers need one place that researches options, compares them on the same basis, produces an itinerary, and gives a cost estimate that says clearly where each number came from.

TravelMate AI is an agent-assisted planner. It researches and compares options, drafts an itinerary, and estimates cost. It does not spend money. Any booking requires explicit human approval, and in the MVP no booking or payment is executed at all.

## 2. Target users

| User | Need |
|---|---|
| Individual traveller | Compare transport and hotel options for a trip and see a realistic total cost. |
| Trip planner (family or small group organiser) | Build and revise an itinerary for several people, with a clear budget. |
| Internal developer / operator | Run the system in mock mode, switch providers on and off, and audit what the agent did. |

## 3. Goals and success measures

| Goal | Measure (MVP) |
|---|---|
| Produce a complete trip plan for the Indore to Goa scenario | End-to-end run produces transport options, hotel options, weather, an itinerary and a cost estimate. |
| Make data provenance visible | 100% of displayed prices and availability show LIVE, CACHED_LIVE or MOCK. |
| Keep money movement safe | Zero booking or payment calls possible while `BOOKING_ENABLED=false`, verified by tests. |
| Keep the system verifiable | All MVP features covered by automated tests that run without network access. |

## 4. Definitions

- **LIVE**: data fetched from an authorized provider integration during the current request or within that provider's freshness window.
- **CACHED_LIVE**: data that originated from a provider but is older than its freshness window. It is shown with its retrieval timestamp and marked stale.
- **MOCK**: deterministic fixture data. It is always labelled MOCK in the API response and the UI.
- **Estimate**: a computed figure (for example, a total cost) built from inputs of any provenance. It inherits the lowest provenance of its inputs.
- **Quote**: a provider-supplied price for a specific option at a specific time, with an expiry.

## 5. Scope

### 5.1 Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Accept a trip request: origin, destination, trip type (one-way or round trip), departure date, return date (round trip only; a same-day return is allowed), number of travellers, budget (optional), preferences (optional). | Must |
| FR-02 | Research transport options (flight, train, bus, road) between origin and destination through the transport provider interface. | Must |
| FR-03 | Research hotel options at the destination for the given dates and occupancy through the hotel provider interface. | Must |
| FR-04 | Retrieve weather for the destination and travel dates through the weather provider interface, with forecast-horizon limits reported. | Must |
| FR-05 | Compare options side by side on price, duration, stops, rating, and cancellation terms where the provider supplies them. | Must |
| FR-06 | Generate a day-by-day itinerary draft that uses the selected transport, hotel and weather information. | Must |
| FR-07 | Estimate total trip cost (transport, accommodation, local transport allowance, contingency) with an itemised breakdown and a provenance label per line. | Must |
| FR-08 | Produce a trip summary the user can review, edit, and save. | Must |
| FR-09 | Persist trips, searches, quotes, itineraries, and agent decisions. | Must |
| FR-10 | Let a user create a booking *intent* for a chosen option. Intent is recorded only; no provider booking call is made in the MVP. | Must |
| FR-11 | Require explicit human approval (FR-12) before any future booking step. | Must |
| FR-12 | Record an approval as a distinct, auditable action bound to a specific quote snapshot. | Must |
| FR-13 | Re-check the quote before any booking step and block the step if the price or availability has changed. | Must (for the booking milestone) |
| FR-14 | Support mock providers for every external data type, selectable per provider. | Must |
| FR-15 | Ask the user for clarification when required trip inputs are missing. | Should |
| FR-16 | Let a user compare two itinerary versions. | Could |
| FR-17 | Let the user hold a spoken conversation with the planner in Hindi, Hinglish or English. The spoken flow uses the same planning tools, validation and provenance rules as the text flow, offers a text fallback, and cannot approve or execute a booking. Not part of the MVP until the voice milestones in `docs/VOICE_ASSISTANT_PLAN.md` pass. Language support per provider is unverified. | Could |
| FR-18 | Show flights, trains and buses as separate, comparable categories with fields that fit each mode, and let the user walk through a clearly labelled **simulated** booking of a mock option. A simulated booking reserves nothing, issues no ticket, collects no payment, and is never a provider confirmation (ADR 0003). Real booking and payment stay disabled. Mock data only until a live provider is authorised (Q1). | Could |

### 5.2 Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Correctness | No value is shown as LIVE unless it came from an authorized provider with a retrieval timestamp. |
| NFR-02 | Safety | Booking and payment are disabled by default (`BOOKING_ENABLED=false`). Enabling them requires code and configuration changes that are reviewed. |
| NFR-03 | Security | Secrets come only from environment variables or a secret store. None are committed. See `docs/SECURITY.md`. |
| NFR-04 | Testability | Unit and integration tests run with no network access and no real API keys. Provider and LLM calls are replaced by fakes in tests. |
| NFR-05 | Observability | Each request and agent run has an identifier. Logs are structured and redact sensitive fields. |
| NFR-06 | Reliability | Provider failures degrade the result (partial results with an explanation) instead of failing the whole plan. Retries are bounded. |
| NFR-07 | Performance | A mock-mode plan for the Indore to Goa scenario completes in under 10 seconds on a developer machine. Live-mode targets are set after provider selection. |
| NFR-08 | Maintainability | Python 3.12. Typed code checked in CI. Changes are small and reviewed. |
| NFR-09 | Cost control | LLM calls and provider calls are counted per run and can be capped by configuration. |
| NFR-10 | Accuracy of money | Monetary amounts are stored as integer minor units with an ISO 4217 currency code. Floating-point arithmetic is not used for money. |
| NFR-11 | Time | Timestamps are stored in UTC. Local times are shown with the destination time zone. |
| NFR-12 | Accessibility | The web UI meets WCAG 2.1 AA for the core planning flow (target; verified before release). |

## 6. MVP scope

Included:
- Trip request intake with validation and clarification questions (FR-01, FR-15). One-way, round-trip and same-day return trips are supported.
- Transport, hotel, and weather research through provider interfaces, with **mock providers only** (FR-02 to FR-04, FR-14).
- Option comparison and itinerary drafting (FR-05, FR-06).
- Cost estimation with provenance (FR-07).
- Persistence of trips and agent runs (FR-09).
- Booking intent creation and approval records, with execution disabled (FR-10 to FR-12).
- Web UI for the planning flow and a provenance display.
- The Indore to Goa scenario as the acceptance fixture.

Not included in the MVP:
- Real provider bookings, payments, refunds, or cancellations.
- Live provider integrations. These require authorization and a separate milestone.
- Multi-currency conversion with live exchange rates.
- Visa, insurance, or legal travel advice.
- Mobile apps.
- Multi-user collaboration on a trip.
- Background jobs, queues, and scheduled price tracking. (Redis and Celery are deferred until a requirement justifies them.)

## 7. User journey (Indore to Goa)

1. The user enters origin **Indore**, destination **Goa**, the trip type, the departure date and (for a round trip) the return date, traveller count and an optional budget.
2. The system checks whether required fields are present. If not, it asks targeted questions.
3. The planner runs transport, hotel and weather research in parallel. Each result carries its provenance label. Failed providers are reported, not hidden.
4. The user sees a comparison table of transport options and hotel options, with provenance and timestamps.
5. The user selects one transport option and one hotel option.
6. The system drafts an itinerary and computes a cost estimate with an itemised breakdown.
7. The user edits the itinerary if needed and saves the trip.
8. The user may create a booking intent for the selected options. The UI states that no booking is made and that a human must approve any future booking.
9. The run and all decisions are recorded in the audit log.

## 8. Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-01 | Given the Indore to Goa request in mock mode, the system returns at least one transport option, one hotel option, a weather summary, an itinerary, and a cost estimate. | Automated end-to-end test. |
| AC-02 | Every price, availability value and weather value in the response has a provenance field with one of LIVE, CACHED_LIVE or MOCK. | Schema test. |
| AC-03 | The cost estimate total equals the sum of its line items in integer minor units. | Unit test. |
| AC-04 | A provider that raises an error produces a partial result with an error entry for that provider. The other providers' results are still returned. | Unit test with a failing fake. |
| AC-05 | With `BOOKING_ENABLED=false`, the booking-intent endpoint records the intent and never calls a booking client. | Test with a spy on the booking client. |
| AC-06 | An approval is rejected if it references a quote that has expired or has a different price than the stored snapshot. | Unit test (booking milestone). |
| AC-07 | The LLM is accessed only through the `LLMClient` interface. Tests run with a fake LLM and no network. | Dependency and unit tests. |
| AC-08 | No secret appears in logs, API responses, or repository files. | Log-redaction test and secret scan in CI. |
| AC-09 | Missing mandatory inputs produce clarification questions and no provider calls. | Unit test. |
| AC-10 | The planning flow works at a 375 px mobile width without horizontal scrolling. | Browser test (frontend milestone). |

## 9. Mock-data versus live-data requirements

- Mock data is produced only by mock provider implementations. Mock records are deterministic for a given input and carry `provenance: MOCK`.
- Mock data must not be presented as real prices, schedules, or availability. The UI shows a persistent banner when any MOCK data is used in a plan.
- The mode is set per provider category (transport, hotel, weather) by configuration. A plan may mix modes, and the mix is shown in the result.
- Switching a provider from MOCK to LIVE does not change the API contract. Only the provenance label changes.
- Live data is never fabricated to fill a gap. If a live provider returns nothing, the result is empty for that category with a reason.
- Mock fixtures must not be used as examples of live fares or schedules in documentation or marketing text.
- Each live response must store the provider name, retrieval time, and the freshness window applied.

## 10. Assumptions

- A1: The MVP is a single-tenant, locally run application for development and internal evaluation. Public deployment is out of scope for the MVP.
- A2: The Indore to Goa route is used as a scenario in mock mode. Any real route, schedule, or fare facts must come from a provider, not from this document.
- A3: The OpenAI API is the first LLM provider, accessed through a replaceable interface.
- A4: Weather is queried through a provider interface. The specific weather service is not yet selected.
- A5 (provisional, M2): Source metadata for MOCK records has the same four fields as live records (§9: switching MOCK to LIVE does not change the API contract).
- A6 (provisional, M2): Availability is one of AVAILABLE, UNAVAILABLE or UNKNOWN, and defaults to UNKNOWN. Quote fees are itemised separately from the price and use the price's currency. Provider-quoted prices and fees are not negative.
- A7 (provisional, M2): An itinerary identifies days by number. Calendar dates are worked out by code, never written by the LLM.
- A8 (provisional, M2): Run statuses other than `stopped_limit` (ARCHITECTURE §8) are inferred from the human pauses in ARCHITECTURE §4 and §7.
- A9 (provisional, M2): Trip dates are calendar dates with no time zone attached. A quote or approval counts as expired from the instant its expiry time is reached.
- A10 (provisional, M3): A weather forecast has, per day, a summary, optional minimum and maximum temperature in °C and an optional chance of rain (0 to 100 %), and reports the requested dates it does not cover. Weather is not an option the user selects.
- A11 (provisional, M3): Provider interfaces are synchronous and read-only, and a search query is one leg or one stay (a hotel query needs at least one night; rooms are not modelled). The retry backoff delay (a random fraction of 0.25 s doubling per retry) is a choice, because ARCHITECTURE §9 fixes only the timeout (5 s) and the retry count (2). Mock providers cover only Indore and Goa (both directions) and return nothing for any other place.
- A12 (provisional, M4 and M5): A provider failure becomes an error entry in the tool result and never hides the other categories; an empty result always carries a reason. Options are sorted by their price as quoted, missing values last, and cancellation terms are grouped only by whether they were supplied. The cost estimator makes no decision for the caller: quantities, the contingency rule (percentage, rounding mode, base) and which lines do not apply are all explicit inputs, and anything required but not supplied is listed as missing. A mix of LIVE and CACHED_LIVE is labelled CACHED_LIVE, and "within budget" means the total equals the budget exactly.
- A13 (provisional, M6): The itinerary drafter shows the model only run-scoped aliases for options (`option-1`, ...), descriptive names, weather text keyed by day number, a traveller count and the user's notes; never prices, availability, times, dates or provider IDs. An unusable answer, or one that refers to an unknown option, gets one repair attempt; a timeout or rate limit gets one retry after a random fraction of 0.5 s (ARCHITECTURE §9 gives no delay). Text that seems to state a price, a time, a date or a booking claim is returned with a warning, not blocked. The caller supplies the number of days. The OpenAI adapter has no real transport and its request format is unverified against the live API.

## 11. Open questions

| # | Question | Owner | Blocks |
|---|---|---|---|
| Q1 | Which transport data providers will be authorized for live use, and under what terms? | Project owner | Live transport (post-MVP) |
| Q2 | Which hotel data provider will be used? | Project owner | Live hotels (post-MVP) |
| Q3 | Which weather provider will be used, and what is its forecast horizon and licence? | Project owner | Live weather |
| Q4 | How is end-user authentication handled (own accounts, external identity provider, or none for the local MVP)? | Project owner | Multi-user deployment |
| Q5 | What currency should the MVP display, and is a currency conversion source needed? | Project owner | Cost display |
| Q6 | What freshness window applies to each provider type? | Project owner | Provenance labelling |
| Q7 | What is the approval expiry for a quote (default proposed: 15 minutes)? | Project owner | Booking milestone |
| Q8 | Which payment model applies (direct provider payment, merchant of record, or none)? | Project owner | Payments (post-MVP) |
| Q9 | When an approval expires or an approved quote lapses, does the booking intent become EXPIRED, or return to AWAITING_APPROVAL for a new approval? Not decided; no such transition is allowed yet. | Project owner | M10 |
| Q10 | May a booking in flight (BOOKING) or an unclear one (NEEDS_REVIEW) be cancelled or expired? How are FAILED and NEEDS_REVIEW resolved? ARCHITECTURE §6 says CANCELLED/EXPIRED are reachable "from any state before CONFIRMED"; the domain table currently allows them only before execution starts. | Project owner | M14 |
| Q11 | Idempotency keys: ARCHITECTURE §5 and plan M10 describe a caller-supplied key on the booking intent; SECURITY §6 describes a key derived from the intent and approval IDs for each booking attempt. Are these two separate keys? | Project owner | M10, M14 |
| Q12 | What is the basis of a quoted price (per traveller, per party, per night)? | Project owner | M3, M5 |
| Q13 | What are the rules for hotel stay windows, the weather window and itinerary length for one-way and same-day trips? | Project owner | M3, M4, M6 |
| Q14 | What are the limits for traveller count and preferences text, and the rules for a budget (positive? currency, see Q5)? | Project owner | M7 (intake), M8 |
| Q15 | How is a quote's content hash built (algorithm, exact inputs including traveller details)? | Project owner | M10 |
| Q16 | What is the order of LIVE and CACHED_LIVE when an estimate mixes them ("lowest provenance")? Currently a mix is labelled CACHED_LIVE. | Project owner | M5 |
| Q17 | What does "within budget" mean: exactly equal to the budget, or inside a tolerance? Currently exactly equal. | Project owner | M5, M8 |
| Q18 | What are the contingency percentage, the lines it applies to, its rounding mode (half up, half even, down or up) and the local transport allowance? The estimator has no defaults for any of them. | Project owner | M7 (wiring) |
| Q19 | Which language model, token limit, timeout and prompt-size limit apply, and who supplies the API key? The LLM layer has no defaults for the limits and never makes a live call without your key and approval. | Project owner | M7 (wiring), first live call |
