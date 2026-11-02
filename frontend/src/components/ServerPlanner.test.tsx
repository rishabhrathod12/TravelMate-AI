import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { TripRequest } from "../contracts/types";
import { ServerPlanner } from "./ServerPlanner";

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

function transport(id: string, mode: string, operator: string, paise: number) {
  return {
    id,
    source: SOURCE,
    availability: "AVAILABLE",
    cancellation_terms: null,
    mode,
    origin: { name: "Indore" },
    destination: { name: "Goa" },
    departs_at: "2026-12-01T06:00:00Z",
    arrives_at: "2026-12-01T09:00:00Z",
    stops: 0,
    price: { amount_minor: paise, currency: "INR" },
    operator_name: operator,
    service_label: "S1",
    details: null,
  };
}

const HOTEL = {
  id: "h1",
  source: { ...SOURCE, provider_name: "mock-hotels" },
  availability: "AVAILABLE",
  cancellation_terms: null,
  name: "Sea View",
  location: { name: "Goa" },
  nightly_rate: { amount_minor: 300000, currency: "INR" },
};

const WAITING = {
  run_id: "r1",
  trip_id: "t1",
  status: "awaiting_selection",
  waiting_for: { transport: ["a"], return_transport: ["b"], hotels: ["h1"] },
  research: {
    transport: { options: [transport("a", "FLIGHT", "FakeAir", 500000)] },
    return_transport: { options: [transport("b", "TRAIN", "FakeRail", 100000)] },
    hotels: { options: [HOTEL] },
  },
  summary: null,
  error: null,
};

const ESTIMATE = {
  currency: "INR",
  missing_items: ["local transport"],
  lines: [
    { kind: "TRANSPORT", description: "Flight", amount: { amount_minor: 1000000, currency: "INR" }, provenance: "MOCK" },
    { kind: "ACCOMMODATION", description: "Hotel", amount: { amount_minor: 1200000, currency: "INR" }, provenance: "MOCK" },
  ],
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubServer(routes: Record<string, () => Response>) {
  const spy = vi.fn<typeof fetch>((input, init) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const route = routes[key];
    if (route === undefined) {
      return Promise.reject(new Error(`unexpected request ${key}`));
    }
    return Promise.resolve(route());
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("starting", () => {
  test("it asks for the number of rooms and does not guess it", async () => {
    stubServer({});
    render(<ServerPlanner request={REQUEST} />);

    const start = screen.getByRole("button", { name: "Plan with the server" });
    expect(start).toBeDisabled();
    expect((screen.getByLabelText(/Rooms needed/) as HTMLInputElement).value).toBe("");

    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "0" } });
    expect(start).toBeDisabled();
  });

  test("it says plainly that nothing is booked", () => {
    render(<ServerPlanner request={REQUEST} />);

    expect(screen.getByText(/Nothing is booked/)).toBeInTheDocument();
  });
});

describe("the whole flow against a stubbed server", () => {
  test("options show their provenance, the choice is sent and the estimate is shown", async () => {
    const spy = stubServer({
      "POST /api/v1/trips": () => json({ id: "t1" }, 201),
      "POST /api/v1/trips/t1/runs": () => json(WAITING, 202),
      "POST /api/v1/runs/r1/selections": () => json({ ...WAITING, status: "running", waiting_for: null, research: null }, 202),
      "GET /api/v1/runs/r1": () =>
        json({ ...WAITING, status: "completed", waiting_for: null, summary: { estimate: ESTIMATE } }),
    });
    render(<ServerPlanner request={REQUEST} />);

    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan with the server" }));

    expect(await screen.findByText("Choose from what the server found")).toBeInTheDocument();
    expect(screen.getByText(/FLIGHT FakeAir/)).toBeInTheDocument();
    expect(screen.getAllByText(/Sample data/).length).toBeGreaterThanOrEqual(3);

    const use = screen.getByRole("button", { name: "Use these choices" });
    expect(use).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/FLIGHT FakeAir/));
    fireEvent.click(screen.getByLabelText(/TRAIN FakeRail/));
    fireEvent.click(screen.getByLabelText(/Sea View/));
    expect(use).toBeEnabled();
    fireEvent.click(use);

    expect(await screen.findByText("Estimate from the server", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("Total of the lines shown")).toBeInTheDocument();
    expect(screen.getByText(/Not priced: local transport/)).toBeInTheDocument();
    expect(screen.getByText("Incomplete")).toBeInTheDocument();

    const created = JSON.parse((spy.mock.calls[0]?.[1] as RequestInit).body as string);
    expect(created.rooms).toBe(1);
    const selectionCall = spy.mock.calls.find(([url]) => String(url).endsWith("/selections"));
    expect(JSON.parse((selectionCall?.[1] as RequestInit).body as string)).toEqual({
      transport_id: "a",
      return_transport_id: "b",
      hotel_id: "h1",
    });
  });

  test("every leg must be chosen: the button stays off while any one is missing", async () => {
    stubServer({
      "POST /api/v1/trips": () => json({ id: "t1" }, 201),
      "POST /api/v1/trips/t1/runs": () => json(WAITING, 202),
    });
    render(<ServerPlanner request={REQUEST} />);
    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan with the server" }));
    await screen.findByText("Choose from what the server found");
    const use = screen.getByRole("button", { name: "Use these choices" });

    fireEvent.click(screen.getByLabelText(/TRAIN FakeRail/));
    fireEvent.click(screen.getByLabelText(/Sea View/));
    expect(use).toBeDisabled(); // the outbound transport is missing

    fireEvent.click(screen.getByLabelText(/FLIGHT FakeAir/));
    expect(use).toBeEnabled();
  });

  test("a run that is still working is read again until it asks for a choice", async () => {
    let reads = 0;
    stubServer({
      "POST /api/v1/trips": () => json({ id: "t1" }, 201),
      "POST /api/v1/trips/t1/runs": () => json({ ...WAITING, status: "running", waiting_for: null, research: null }, 202),
      "GET /api/v1/runs/r1": () => {
        reads += 1;
        return json(WAITING);
      },
    });
    render(<ServerPlanner request={REQUEST} />);

    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan with the server" }));

    expect(await screen.findByText("The server is researching")).toBeInTheDocument();
    expect(await screen.findByText("Choose from what the server found", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(reads).toBe(1);
  });
});

describe("when something goes wrong", () => {
  test("the server's own words are shown and the form comes back", async () => {
    stubServer({
      "POST /api/v1/trips": () => json({ detail: "Too many planning runs were started. Try again later." }, 429),
    });
    render(<ServerPlanner request={REQUEST} />);

    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan with the server" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many planning runs");
    await waitFor(() => expect(screen.getByRole("button", { name: "Plan with the server" })).toBeEnabled());
  });

  test("an unreachable server is explained", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("failed"))));
    render(<ServerPlanner request={REQUEST} />);

    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan with the server" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be reached");
  });

  test("a failed run shows the server's note", async () => {
    stubServer({
      "POST /api/v1/trips": () => json({ id: "t1" }, 201),
      "POST /api/v1/trips/t1/runs": () =>
        json({ ...WAITING, status: "failed", waiting_for: null, research: null, error: "The run stopped." }, 202),
    });
    render(<ServerPlanner request={REQUEST} />);

    fireEvent.change(screen.getByLabelText(/Rooms needed/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan with the server" }));

    expect(await screen.findByText("The run stopped.")).toBeInTheDocument();
  });
});
