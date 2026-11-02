import { afterEach, describe, expect, test, vi } from "vitest";

import {
  PlanningApiError,
  chooseOptions,
  createTrip,
  draftFromRequest,
  getRun,
  isWorking,
  startRun,
} from "./planning";
import type { TripRequest } from "../contracts/types";

const REQUEST: TripRequest = {
  trip_type: "ROUND_TRIP",
  origin: { name: "Indore" },
  destination: { name: "Goa" },
  departure_date: "2026-12-01",
  return_date: "2026-12-05",
  travellers: [{ age: null }, { age: null }],
  preferences: null,
};

const SOURCE = {
  provenance: "MOCK",
  provider_name: "mock-transport",
  retrieved_at: "2026-01-01T00:00:00Z",
  freshness_window_seconds: 900,
};

const RUN = {
  run_id: "r1",
  trip_id: "t1",
  status: "awaiting_selection",
  waiting_for: { transport: ["a"], return_transport: ["b"], hotels: ["h"] },
  research: {
    transport: { options: [{ id: "a", source: SOURCE }] },
    return_transport: { options: [{ id: "b", source: SOURCE }] },
    hotels: { options: [{ id: "h", source: SOURCE }] },
  },
  summary: null,
  error: null,
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubFetch(next: () => Response | Error) {
  const spy = vi.fn<typeof fetch>(() => {
    const result = next();
    return result instanceof Response ? Promise.resolve(result) : Promise.reject(result);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the requests", () => {
  test("a trip is created from the request, with the rooms exactly as given", async () => {
    const spy = stubFetch(() => json({ id: "t1" }, 201));

    const id = await createTrip("Indore to Goa", REQUEST, 2);

    expect(id).toBe("t1");
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/trips");
    expect(JSON.parse(init.body as string)).toEqual({
      title: "Indore to Goa",
      draft: draftFromRequest(REQUEST),
      rooms: 2,
    });
  });

  test("the draft carries names, dates and the traveller count, not invented fields", () => {
    expect(draftFromRequest(REQUEST)).toEqual({
      origin: "Indore",
      destination: "Goa",
      trip_type: "ROUND_TRIP",
      departure_date: "2026-12-01",
      return_date: "2026-12-05",
      traveller_count: 2,
      preferences: null,
    });
  });

  test("start, read and choose use the right method and an encoded path", async () => {
    const spy = stubFetch(() => json(RUN, 202));

    await startRun("t/1");
    await getRun("r 1");
    await chooseOptions("r 1", { transportId: "a", returnTransportId: "b", hotelId: "h" });

    const calls = spy.mock.calls.map(([url, init]) => [(init as RequestInit).method, url]);
    expect(calls).toEqual([
      ["POST", "/api/v1/trips/t%2F1/runs"],
      ["GET", "/api/v1/runs/r%201"],
      ["POST", "/api/v1/runs/r%201/selections"],
    ]);
    const body = JSON.parse((spy.mock.calls[2]?.[1] as RequestInit).body as string);
    expect(body).toEqual({ transport_id: "a", return_transport_id: "b", hotel_id: "h" });
  });
});

describe("reading a run", () => {
  test("the choices and the options are read with their provenance intact", async () => {
    stubFetch(() => json(RUN));

    const run = await getRun("r1");

    expect(run.status).toBe("awaiting_selection");
    expect(run.choices).toEqual({ transport: ["a"], returnTransport: ["b"], hotels: ["h"] });
    expect(run.research?.transport[0]?.source.provenance).toBe("MOCK");
    expect(isWorking(run)).toBe(false);
  });

  test("a run that is still working is reported as working", async () => {
    stubFetch(() => json({ ...RUN, status: "running", waiting_for: null, research: null }));

    expect(isWorking(await getRun("r1"))).toBe(true);
  });

  test("an unknown status is refused rather than guessed at", async () => {
    stubFetch(() => json({ ...RUN, status: "mystery" }));

    await expect(getRun("r1")).rejects.toMatchObject({ detail: expect.stringContaining("shape") });
  });

  test("an option without a source is refused: no value without provenance", async () => {
    stubFetch(() => json({ ...RUN, research: { transport: { options: [{ id: "a" }] } } }));

    await expect(getRun("r1")).rejects.toBeInstanceOf(PlanningApiError);
  });

  test("a finished run carries the estimate from the summary", async () => {
    const estimate = { currency: "INR", lines: [], missing_items: ["local transport"] };
    stubFetch(() =>
      json({ ...RUN, status: "completed", waiting_for: null, summary: { estimate } }),
    );

    const run = await getRun("r1");

    expect(run.estimate).toEqual(estimate);
  });
});

describe("failures", () => {
  test("a Problem Details body gives its detail and code", async () => {
    stubFetch(() => json({ detail: "Too many runs were started.", code: "x" }, 429));

    await expect(startRun("t1")).rejects.toMatchObject({
      status: 429,
      detail: "Too many runs were started.",
      code: "x",
    });
  });

  test("a body that is not JSON still gives the status", async () => {
    stubFetch(() => new Response("oops", { status: 502 }));

    await expect(startRun("t1")).rejects.toMatchObject({ status: 502, detail: null });
  });

  test("an unreachable server has no status", async () => {
    stubFetch(() => new TypeError("failed to fetch"));

    await expect(startRun("t1")).rejects.toMatchObject({ status: null });
  });
});

const FORECAST = {
  location: { name: "Goa" },
  requested_start: "2026-12-01",
  requested_end: "2026-12-05",
  days: [
    { day: "2026-12-01", summary: "Sunny", temperature_min_c: 24, temperature_max_c: 31, precipitation_chance_percent: 5 },
    { day: "2026-12-02", summary: "Light rain", temperature_min_c: null, temperature_max_c: 28, precipitation_chance_percent: null },
  ],
  source: { ...SOURCE, provider_name: "mock-weather" },
};

describe("weather, provider problems and notes", () => {
  test("the forecast is read while the run waits for a choice, with its source label", async () => {
    stubFetch(() => json({ ...RUN, research: { ...RUN.research, weather: { forecast: FORECAST, errors: [], empty_reason: null } } }));

    const run = await getRun("r1");

    expect(run.weather?.location).toBe("Goa");
    expect(run.weather?.start).toBe("2026-12-01");
    expect(run.weather?.end).toBe("2026-12-05");
    expect(run.weather?.days).toHaveLength(2);
    expect(run.weather?.source?.provenance).toBe("MOCK");
  });

  test("the forecast is also read from the summary of a finished run", async () => {
    stubFetch(() =>
      json({ ...RUN, status: "completed", waiting_for: null, summary: { weather: { forecast: FORECAST, errors: [], empty_reason: null } } }),
    );

    expect((await getRun("r1")).weather?.days[0]?.summary).toBe("Sunny");
  });

  test("a value the provider left out stays missing: it is never turned into zero", async () => {
    stubFetch(() => json({ ...RUN, research: { weather: { forecast: FORECAST, errors: [], empty_reason: null } } }));

    const days = (await getRun("r1")).weather?.days ?? [];

    expect(days[0]).toEqual({ day: "2026-12-01", summary: "Sunny", temperatureMinC: 24, temperatureMaxC: 31, rainChancePercent: 5 });
    expect(days[1]).toEqual({ day: "2026-12-02", summary: "Light rain", temperatureMinC: null, temperatureMaxC: 28, rainChancePercent: null });
  });

  test("no forecast, with the reason, is kept so the screen can say why", async () => {
    stubFetch(() => json({ ...RUN, research: { weather: { forecast: null, errors: [], empty_reason: "Too far ahead." } } }));

    const weather = (await getRun("r1")).weather;

    expect(weather?.days).toEqual([]);
    expect(weather?.emptyReason).toBe("Too far ahead.");
  });

  test("a run with no weather has none", async () => {
    stubFetch(() => json(RUN));

    expect((await getRun("r1")).weather).toBeNull();
  });

  test("a forecast of the wrong shape is refused rather than half used", async () => {
    stubFetch(() => json({ ...RUN, research: { weather: { forecast: { ...FORECAST, days: "rain" }, errors: [] } } }));

    await expect(getRun("r1")).rejects.toMatchObject({ detail: expect.stringContaining("shape") });
  });

  test("providers that failed are read, as text, and the rest of the answer is kept", async () => {
    stubFetch(() =>
      json({
        ...RUN,
        status: "completed",
        waiting_for: null,
        summary: {
          provider_errors: [{ provider_name: "mock-hotels", kind: "TIMEOUT", message: "Timed out <b>twice</b>" }],
          notes: ["No hotel was searched: this trip has no hotel stay."],
        },
      }),
    );

    const run = await getRun("r1");

    expect(run.providerIssues).toEqual([{ provider: "mock-hotels", message: "Timed out <b>twice</b>" }]);
    expect(run.notes).toEqual(["No hotel was searched: this trip has no hotel stay."]);
  });

  test("a malformed list of provider problems is refused", async () => {
    stubFetch(() => json({ ...RUN, status: "completed", waiting_for: null, summary: { provider_errors: [{ provider_name: 7 }] } }));

    await expect(getRun("r1")).rejects.toBeInstanceOf(PlanningApiError);
  });
});
