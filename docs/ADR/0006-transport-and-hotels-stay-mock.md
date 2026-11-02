# ADR 0006: Transport and hotels stay MOCK in the MVP

Status: **Accepted by the project owner on 2026-11-02.**
Date: 2026-11-02
Plan: `docs/IMPLEMENTATION_PLAN.md` M13. Questions: `docs/PRD.md` Q1 (transport) and Q2 (hotels), both answered here. Related: ADR 0005 (live weather).

## Context

M13 replaces mock adapters with authorised live ones, one category at a time, and needs a provider, reviewed terms and an owner-supplied credential for each (`docs/IMPLEMENTATION_PLAN.md` M13 preconditions). Weather has such a provider (ADR 0005). On 2026-11-02 the project researched hotels and then transport, reading only public pages: no account was created, no key was used and no provider API was called.

The question for each category was whether a provider exists that an individual developer, with no business agreement, can use legitimately for live, correctly labelled data. For hotels and transport the answer found was no.

## Decision

- **Hotels stay MOCK.** The owner decided this on 2026-11-02 after the hotel research.
- **Transport (flights, trains and buses) stays MOCK.** The owner decided this on 2026-11-02 after the transport research.
- The `PROVIDER_MODE_*` setting keeps refusing `live` for these two categories. Mock and live can be mixed per category, so the UI can show weather as live next to MOCK transport and hotels.
- **Unofficial routes are rejected on purpose:** scraping a booking site, or using a third-party scraper of IRCTC or redBus, is not used, because it risks breaching those operators' terms and could break without notice.
- This is a decision for the MVP, not a permanent one. See "When to revisit".

## Evidence

Read on 2026-11-02. "First-party" means the provider's own page was read; otherwise the claim comes from news or third-party pages and is marked.

**Hotels**
- Booking.com Demand API: needs registration as a Booking.com Managed Affiliate Partner and Partner Centre access before a key or the sandbox is available (first-party, [try-out page](https://developers.booking.com/demand/docs/getting-started/try-out-the-api)). Its pages disagree on sandbox limits (20 and 50 requests a minute).
- Hotelbeds (APItude): a self-serve test key capped at 50 requests a day, with better quotas through certification (first-party, [getting started](https://developer.hotelbeds.com/documentation/getting-started/)). Its page does not say whether test prices are real, what production access needs, or what the content and image terms are. This is the one option that could be tried; it was not chosen.
- Amadeus: its self-service portal reportedly shut down on 17 July 2026, leaving hotel APIs to Enterprise customers. **Not confirmed first-party** (its site returned no content and the news article returned a 403); the claim comes from news and third-party reports.
- Expedia Rapid: not verified (its site could not be fetched). Believed partner-gated.
- Travelpayouts / Hotellook: prices come from a cache of earlier searches, kept 2 to 7 days, and the search API is on request (third-party and marketing pages). Cached data of that age could not honestly be labelled LIVE against a 3-hour window.

**Transport**
- Flights, Duffel: the only self-serve option. A test token needs only a sign-up. Pricing is $3.00 per confirmed order, 1% for managed content and $2.00 per paid ancillary, plus $0.005 per search above a 1,500 searches per booking ratio (first-party, [pricing page](https://duffel.com/pricing)). Not established: whether test-mode fares are simulated (a third-party source says they book a fake airline "Duffel Airways"), what live access requires, how searches are counted when an app never books, and whether it carries IndiGo or Air India domestic fares, which Indore to Goa needs.
- Flights, Skyscanner: partners only and manually approved; reportedly forbids caching prices (third-party reports).
- Trains, IRCTC and Indian Railways: no official public API or partner programme found. The older eRail API is suspended. Community tools automate the IRCTC website.
- Buses, redBus: no official developer portal or public partner programme found. Scrapers exist and likely breach its terms.

## Consequences

- **The MVP's live data is weather only.** Everything about transport and hotels, including prices, availability and cancellation terms, stays a labelled MOCK fixture and is never shown as live. This keeps NFR-01 (nothing is LIVE without an authorised provider and a timestamp).
- **Cost estimates stay MOCK-labelled.** An estimate's provenance is its weakest line, so any estimate that includes transport or hotels is MOCK even when the weather is live.
- **Booking stays out of reach.** There is no live quote to approve, so M14 has nothing real to book against. The approval path stays built and tested against mock quotes (ADR 0003 and M10 unchanged).
- **No new dependency, credential or external call** is needed for these two categories.

## When to revisit

Reopen this decision, with a new ADR, if any of these becomes true: the owner has or obtains a business relationship or approved partner status with a hotel or transport provider; a provider's own page states a self-serve production tier with terms that allow this use; or the owner wants to try the Hotelbeds test key and accepts what is unknown about its test prices, production access and content terms. Any live adapter then follows the M13 rules: one category at a time, recorded fixtures, contract tests with no network, an opt-in live test run by the owner, and the owner supplying any key.

## Not decided here

Weather is covered by ADR 0005. Payments (PRD Q8) and real booking (M14) are untouched, and `BOOKING_ENABLED` stays false.
