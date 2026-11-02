# ADR 0005: Live weather from Open-Meteo (first M13 category)

Status: **Proposed.** The provider choice was made by the project owner on 2026-11-02. The remaining decisions in "Open decisions" below are the owner's and are not made. No code has been written and no request has been sent to Open-Meteo.
Date: 2026-11-02
Plan: `docs/IMPLEMENTATION_PLAN.md` M13. Questions: `docs/PRD.md` Q3 (answered here), Q6 (open for weather).

## Context

M13 replaces mock adapters with authorised live ones, one category at a time. Weather goes first: it is read-only, has no booking path, and the shortlist research (2026-11-02, from the providers' own pages where reachable) found one provider that needs no account or key.

The weather interface takes a place and a date range and returns one entry per day: a summary, minimum and maximum temperature in degrees Celsius, and a rain-chance percentage from 0 to 100, with the forecast days it cannot cover reported as missing (`app/domain/weather.py`, `app/providers/base.py`).

## Decision

Use **Open-Meteo** (`https://open-meteo.com`) for weather. Transport and hotels stay MOCK. Mock and live can be mixed per category (`PROVIDER_MODE_WEATHER`), and the UI shows which is which.

## What is known about Open-Meteo

From its own pages, read on 2026-11-02 ([terms](https://open-meteo.com/en/terms), [forecast docs](https://open-meteo.com/en/docs)):

- **Free tier is for non-commercial use only.** Its terms name websites or apps with subscriptions or advertising as commercial. A paid plan covers commercial use.
- **Limits:** under 10,000 calls a day, 5,000 an hour and 600 a minute; applied per IP address and application. The operator may block misuse without notice.
- **No API key** is mentioned for the free tier.
- **Licence:** data under CC BY 4.0, so credit and a link to the licence must be given.
- **Forecast horizon:** up to 16 days (`forecast_days` 0 to 16, default 7).
- **Daily fields that fit our type:** `temperature_2m_max`, `temperature_2m_min`, `precipitation_probability_max`, and `weather_code` ("the most severe weather condition on a given day"). `timezone` is required when daily fields are requested.
- **Errors:** a JSON error object with HTTP 400.

Not found on those pages, so unknown: any timeout, any service-level guarantee, any rule about caching or storing responses. Forecast accuracy for Indore and Goa was not assessed. Behaviour when a requested date lies beyond the horizon is not documented (to check when the fixture is recorded).

## Consequences

- **Non-commercial only.** Acceptable for a portfolio project. Any monetisation, including advertising, needs a paid plan and a new decision.
- **Attribution is a requirement, not a nicety.** A live weather value must show its source and the CC BY 4.0 credit wherever the UI shows weather.
- **No guarantees.** A failure is an ordinary outcome: the adapter raises the typed provider errors (timeout, rate limit, unavailable, invalid response) and the run returns a partial result (ARCHITECTURE §9, AC-04). A response that does not parse is rejected whole, never partly used.
- **Data minimisation (SECURITY §7).** Only coordinates and dates would leave the machine. No traveller data, no user or trip identifier, no secret.
- **Provenance.** A live forecast is labelled `LIVE`, with provider `open-meteo`, a retrieval time and a freshness window. A mock is never labelled live and a live value is never labelled mock.
- **Mapping.** `weather_code` is turned into summary text by a fixed table in our code (the WMO codes it uses), so text never comes from the provider and cannot carry instructions (SECURITY §3). `precipitation_probability_max` maps to the rain-chance percentage. Dates beyond the 16-day horizon are reported as missing, never filled in.
- **Tests.** Contract tests run against recorded fixtures and no network (NFR-04). A live smoke test is opt-in, marked `live` and excluded from CI, run by the owner (plan M13).
- **The adapter is a new package** under `app/providers/` that may import a network library. The existing rule that the mocks import none stays.

## Open decisions (the owner's, not made here)

1. **Freshness window for weather (PRD Q6).** How old a forecast may be and still count as LIVE rather than CACHED_LIVE. I suggest 3 hours as a starting point; this is a suggestion, not an answer.
2. **How a place name becomes coordinates.** A `Location` is only a name. Options: (a) a small checked-in table of coordinates and time zones for the places the app supports (Indore and Goa today): deterministic, no extra network call, easy to test, but only those places work; (b) Open-Meteo's geocoding endpoint: handles any place, but it is a second call and sends user-typed place text to a third party. I recommend (a) first.
3. **The HTTP client.** `httpx` is installed only as a dev dependency, and arrives at run time only indirectly through the OpenAI package. Options: declare `httpx` as a run-time dependency (needs the owner's approval, as every addition in ADR 0001 did), or use the standard library's `urllib.request` (no new dependency, plainer timeouts). I recommend declaring `httpx`: it is already installed and makes recorded-fixture tests simple.
4. **Permission to record a fixture.** The plan asks for a real response as a test fixture. That is a few read-only GET requests to a public endpoint, with no key and no personal data. Either the owner runs them, or the owner authorises me to.
5. **Caching.** Whether to cache responses for the freshness window (and so produce CACHED_LIVE) in this first pass, or to call the provider on each plan and label the result LIVE. The simpler second option is the default if the owner says nothing.

## Not decided here

Transport and hotel providers (PRD Q1, Q2), any booking or payment, and any change to authentication. Booking stays off.
