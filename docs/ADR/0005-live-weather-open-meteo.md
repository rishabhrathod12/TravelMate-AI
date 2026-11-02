# ADR 0005: Live weather from Open-Meteo (first M13 category)

Status: **Accepted by the project owner on 2026-11-02** (provider and the five decisions below). **Not implemented:** no adapter exists, no request has been sent to Open-Meteo, and the fixtures are still to be recorded by the owner.
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

## Decisions made by the owner (2026-11-02)

1. **Freshness window for weather (PRD Q6): 3 hours.** A forecast retrieved less than 3 hours ago is `LIVE`; an older one would be `CACHED_LIVE`.
2. **Place to coordinates: a checked-in table.** A small table in our code gives each supported place its latitude, longitude and time zone. No geocoding call, so no typed place text goes to a third party. A place not in the table behaves as it does for the mock: no forecast, reported as missing. Today the table holds Indore and Goa. The owner reviews its values.
3. **HTTP client: declare `httpx` as a run-time dependency** (it was dev-only). Approved. It is added to `backend/pyproject.toml` together with the adapter, with a short comment, as ADR 0001 requires for every dependency.
4. **Fixtures: the owner runs the requests.** Three read-only GET requests, listed below, saved under `backend/tests/fixtures/open_meteo/`. I make no request to Open-Meteo. The fixtures hold no personal data.
5. **Caching: none.** Each plan calls the provider once for the place and labels the result `LIVE` with its retrieval time. `CACHED_LIVE` is not produced in this pass.

## Adapter design agreed with these decisions (not built yet)

- One request per place per plan: `forecast_days=16` and the table's time zone, asking for the four daily fields. Only parameters shown on Open-Meteo's documentation page are used.
- The adapter keeps the requested dates that fall inside the returned days and reports the rest as missing, so no behaviour beyond the documented horizon is relied on.
- A malformed answer is rejected whole as `ProviderInvalidResponse`; a timeout, a 429 or a 5xx maps to the existing typed errors; an HTTP 400 JSON error is `ProviderInvalidResponse` with fixed wording that does not repeat the provider's text.
- The summary text comes from a fixed weather-code table in our code, never from the provider.
- It lives under `app/providers/live/`, so the rule that mocks import no network library is unchanged. Live mode stays refused at startup for transport and hotels, and for weather until the adapter exists and its tests pass.
- Contract tests read the recorded fixtures with no network. The opt-in live smoke test is marked `live`, excluded from CI and run by the owner.

## Fixture requests for the owner

Run in PowerShell from the repository root. The three files must not be edited by hand. Use `curl.exe`, not the `curl` alias.

```powershell
New-Item -ItemType Directory -Force backend\tests\fixtures\open_meteo | Out-Null
curl.exe -s "https://api.open-meteo.com/v1/forecast?latitude=22.7196&longitude=75.8577&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Asia%2FKolkata&forecast_days=16" -o backend\tests\fixtures\open_meteo\indore.json
curl.exe -s "https://api.open-meteo.com/v1/forecast?latitude=15.4909&longitude=73.8278&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Asia%2FKolkata&forecast_days=16" -o backend\tests\fixtures\open_meteo\goa.json
curl.exe -s "https://api.open-meteo.com/v1/forecast?latitude=22.7196&longitude=75.8577&daily=temperature_2m_max&timezone=Asia%2FKolkata&forecast_days=17" -o backend\tests\fixtures\open_meteo\error_forecast_days.json
```

The first two are the normal answers for the two supported places (Goa is placed at Panaji, 15.4909 N, 73.8278 E; Indore at 22.7196 N, 75.8577 E; both are from general knowledge and the owner should check them). The third asks for 17 days, which the documentation says is out of range, to record the real error shape. The recorded time is the files' own modification time and is noted in the fixtures' README when they are added.

## Not decided here

Transport and hotel providers (PRD Q1, Q2), any booking or payment, and any change to authentication. Booking stays off.
