import { vi } from "vitest";

import type { TripRequest } from "../contracts/types";

/** A round trip, so there is a hotel stay and the assistant must ask how many rooms. */
export const ROUND_TRIP: TripRequest = {
  trip_type: "ROUND_TRIP",
  origin: { name: "Indore" },
  destination: { name: "Goa" },
  departure_date: "2026-12-01",
  return_date: "2026-12-05",
  travellers: [{ age: null }, { age: null }],
  preferences: null,
};

/** A one-way trip: no hotel stay, so no question about rooms. */
export const ONE_WAY: TripRequest = {
  trip_type: "ONE_WAY",
  origin: { name: "Indore" },
  destination: { name: "Goa" },
  departure_date: "2026-12-12",
  return_date: null,
  travellers: [{ age: null }],
  preferences: null,
};

export const SOURCE = {
  provenance: "MOCK",
  provider_name: "mock-transport",
  retrieved_at: "2026-01-01T00:00:00Z",
  freshness_window_seconds: 900,
};

function transport(id: string, mode: string, operator: string, label: string, paise: number) {
  return {
    id,
    source: SOURCE,
    availability: "AVAILABLE",
    cancellation_terms: null,
    mode,
    origin: { name: "Indore" },
    destination: { name: "Goa" },
    departs_at: "2026-12-01T06:00:00Z",
    arrives_at: "2026-12-01T09:30:00Z",
    stops: 0,
    price: { amount_minor: paise, currency: "INR" },
    operator_name: operator,
    service_label: label,
    details: null,
  };
}

export const HOTEL = {
  id: "h1",
  source: { ...SOURCE, provider_name: "mock-hotels" },
  availability: "AVAILABLE",
  cancellation_terms: null,
  name: "Sea View",
  location: { name: "Goa" },
  nightly_rate: { amount_minor: 300000, currency: "INR" },
};

/** Five days asked for, three covered: the rest is the forecast horizon and must be reported. */
export const WEATHER = {
  forecast: {
    location: { name: "Goa" },
    requested_start: "2026-12-01",
    requested_end: "2026-12-05",
    days: [
      { day: "2026-12-01", summary: "Sunny", temperature_min_c: 24, temperature_max_c: 31, precipitation_chance_percent: 5 },
      { day: "2026-12-02", summary: "Partly cloudy", temperature_min_c: 23, temperature_max_c: 30, precipitation_chance_percent: 20 },
      { day: "2026-12-03", summary: "Light rain", temperature_min_c: null, temperature_max_c: 28, precipitation_chance_percent: null },
    ],
    source: { ...SOURCE, provider_name: "mock-weather" },
  },
  errors: [],
  empty_reason: null,
};

const RESEARCH = {
  transport: {
    options: [
      transport("a", "FLIGHT", "FakeAir", "F1", 500000),
      transport("t", "TRAIN", "FakeRail", "T1", 90000),
    ],
  },
  return_transport: { options: [transport("b", "FLIGHT", "FakeAir", "F2", 450000)] },
  hotels: { options: [HOTEL] },
  weather: WEATHER,
};

export function runBody(status: string, extra: Record<string, unknown> = {}) {
  return {
    run_id: "r1",
    trip_id: "t1",
    status,
    waiting_for: null,
    research: null,
    summary: null,
    error: null,
    ...extra,
  };
}

export const RUNNING = runBody("running");

export const AWAITING_SELECTION = runBody("awaiting_selection", {
  waiting_for: { kind: "SELECTION", transport: ["a", "t"], return_transport: ["b"], hotels: ["h1"] },
  research: RESEARCH,
});

/** What a one-way trip really offers: outbound options only, no return leg and no hotel. */
export const AWAITING_SELECTION_ONE_WAY = runBody("awaiting_selection", {
  waiting_for: { kind: "SELECTION", transport: ["a", "t"], return_transport: [], hotels: [] },
  research: { ...RESEARCH, return_transport: { options: [] }, hotels: { options: [] } },
});

export const ESTIMATE = {
  currency: "INR",
  missing_items: ["local transport"],
  lines: [
    { kind: "TRANSPORT", description: "Flight out", amount: { amount_minor: 1000000, currency: "INR" }, provenance: "MOCK" },
    { kind: "ACCOMMODATION", description: "Hotel", amount: { amount_minor: 1200000, currency: "INR" }, provenance: "MOCK" },
  ],
};

export const COMPLETED = runBody("completed", {
  research: RESEARCH,
  summary: {
    selection: { transport_id: "a", return_transport_id: "b", hotel_id: "h1" },
    itinerary: {
      days: [{ day_number: 1, items: [{ title: "Travel to Goa", description: null, option_id: "a" }] }],
      notes: null,
    },
    itinerary_warnings: [],
    estimate: ESTIMATE,
    weather: WEATHER,
    provider_errors: [],
    notes: [],
  },
});

/** The finished run of a one-way trip: only the outbound option was chosen, so one approval card. */
export const COMPLETED_ONE_WAY = runBody("completed", {
  research: { ...RESEARCH, return_transport: { options: [] }, hotels: { options: [] } },
  summary: {
    selection: { transport_id: "a", return_transport_id: null, hotel_id: null },
    itinerary: null,
    itinerary_warnings: [],
    estimate: ESTIMATE,
    weather: WEATHER,
    provider_errors: [],
    notes: [],
  },
});

export const INTENT = {
  id: "i1",
  trip_id: "t1",
  status: "AWAITING_APPROVAL",
  category: "TRANSPORT",
  quote: {
    id: "q1",
    option_id: "a",
    price: { amount_minor: 500000, currency: "INR" },
    price_basis: "PER_TRAVELLER",
    fees: [],
    availability: "AVAILABLE",
    cancellation_terms: "Free until 24 hours before",
    valid_until: "2026-12-01T00:00:00Z",
    source: SOURCE,
  },
  quote_content_hash: "a".repeat(64),
  quote_valid_until: "2026-12-01T00:00:00Z",
  availability: "AVAILABLE",
  price_basis: "PER_TRAVELLER",
  travellers: 2,
  approval: null,
  booking_enabled: false,
  notice: "Booking is switched off. Approving records your agreement to these exact terms.",
  request_id: "r",
};

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

type Route = () => Response;

/**
 * Stands in for the planning server. A route is `"METHOD /path"`; give an array to answer the same
 * request differently each time (the last answer repeats). Any request that has no route fails the
 * test, and every request is recorded in `calls`.
 */
export function stubPlanningServer(routes: Record<string, Route | Route[]>) {
  const used = new Map<string, number>();
  const spy = vi.fn<typeof fetch>((input, init) => {
    const key = `${init?.method ?? "GET"} ${String(input).replace(/^https?:\/\/[^/]+/, "")}`;
    const route = routes[key];
    if (route === undefined) {
      return Promise.reject(new Error(`unexpected request ${key}`));
    }
    if (Array.isArray(route)) {
      const index = Math.min(used.get(key) ?? 0, route.length - 1);
      used.set(key, (used.get(key) ?? 0) + 1);
      return Promise.resolve((route[index] as Route)());
    }
    return Promise.resolve(route());
  });
  vi.stubGlobal("fetch", spy);
  const keys = () =>
    spy.mock.calls.map(([input, init]) => `${init?.method ?? "GET"} ${String(input).replace(/^https?:\/\/[^/]+/, "")}`);
  const bodyOf = (key: string): unknown => {
    const call = spy.mock.calls.find(
      ([input, init]) => `${init?.method ?? "GET"} ${String(input).replace(/^https?:\/\/[^/]+/, "")}` === key,
    );
    return call?.[1]?.body === undefined ? undefined : JSON.parse(String(call[1].body));
  };
  return { spy, keys, bodyOf };
}
