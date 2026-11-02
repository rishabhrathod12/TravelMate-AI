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
