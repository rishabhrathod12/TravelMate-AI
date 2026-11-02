import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { createIntent } from "../api/booking";
import type { PlanningRun } from "../api/planning";
import { ServerBooking } from "./ServerBooking";

const SOURCE = {
  provenance: "MOCK",
  provider_name: "mock-transport",
  retrieved_at: "2026-01-01T00:00:00Z",
  freshness_window_seconds: 900,
};
const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);

function intent(overrides: Record<string, unknown> = {}, price = 500000, hash = HASH_A) {
  return {
    id: "i1",
    trip_id: "t1",
    status: "AWAITING_APPROVAL",
    category: "TRANSPORT",
    quote: {
      id: "q1",
      option_id: "a",
      price: { amount_minor: price, currency: "INR" },
      price_basis: "PER_TRAVELLER",
      fees: [{ label: "Convenience fee", amount: { amount_minor: 15000, currency: "INR" } }],
      availability: "AVAILABLE",
      cancellation_terms: "Free until 24 hours before",
      valid_until: "2026-12-01T00:00:00Z",
      source: SOURCE,
    },
    quote_content_hash: hash,
    quote_valid_until: "2026-12-01T00:00:00Z",
    availability: "AVAILABLE",
    price_basis: "PER_TRAVELLER",
    travellers: 2,
    approval: null,
    booking_enabled: false,
    notice: "Booking is switched off. Approving records your agreement to these exact terms.",
    request_id: "r",
    ...overrides,
  };
}

const RUN: PlanningRun = {
  runId: "r1",
  tripId: "t1",
  status: "completed",
  choices: null,
  research: {
    transport: [
      {
        id: "a",
        source: SOURCE,
        availability: "AVAILABLE",
        cancellation_terms: null,
        mode: "FLIGHT",
        origin: { name: "Indore" },
        destination: { name: "Goa" },
        departs_at: "2026-12-01T06:00:00Z",
        arrives_at: "2026-12-01T09:00:00Z",
        stops: 0,
        price: { amount_minor: 500000, currency: "INR" },
        operator_name: "FakeAir",
        service_label: "S1",
        details: null,
      },
    ],
    returnTransport: [],
    hotels: [],
  } as unknown as PlanningRun["research"],
  estimate: null,
  error: null,
  questions: [],
  selected: { transportId: "a", returnTransportId: null, hotelId: null },
  itinerary: null,
  itineraryWarnings: [],
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubServer(routes: Record<string, () => Response>) {
  const spy = vi.fn<typeof fetch>((input, init) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const route = routes[key];
    return route === undefined
      ? Promise.reject(new Error(`unexpected request ${key}`))
      : Promise.resolve(route());
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

function bodyOf(spy: ReturnType<typeof stubServer>, key: string): unknown {
  const call = spy.mock.calls.find(([input, init]) => `${init?.method ?? "GET"} ${String(input)}` === key);
  return JSON.parse(String(call?.[1]?.body));
}

describe("the approval step", () => {
  test("nothing is requested until the traveller asks for the terms", () => {
    const spy = stubServer({});
    render(<ServerBooking run={RUN} />);

    expect(screen.getAllByText(/nothing is booked/i).length).toBeGreaterThan(0);
    expect(spy).not.toHaveBeenCalled();
  });

  test("it shows the exact terms with their provenance, and booking stays switched off", async () => {
    const spy = stubServer({ "POST /api/v1/trips/t1/booking-intents": () => json(intent(), 201) });
    render(<ServerBooking run={RUN} />);

    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));

    expect(await screen.findByText("Free until 24 hours before")).toBeInTheDocument();
    expect(screen.getByText(/per traveller/)).toBeInTheDocument();
    expect(screen.getByText("Convenience fee")).toBeInTheDocument();
    expect(screen.getByText(/MOCK · demo data/)).toBeInTheDocument();
    expect(screen.getByText(/Booking is switched off\. Approving records/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Book (switched off)" })).toBeDisabled();
    const sent = bodyOf(spy, "POST /api/v1/trips/t1/booking-intents") as Record<string, string>;
    expect(sent).toMatchObject({ category: "TRANSPORT", option_id: "a" });
    expect(sent.idempotency_key.length).toBeGreaterThanOrEqual(8);
  });

  test("approving sends the fingerprint of the terms on screen and records agreement only", async () => {
    const approved = intent({
      status: "APPROVED",
      approval: {
        id: "ap1",
        approved_at: "2026-11-02T10:00:00Z",
        expires_at: "2026-11-02T10:15:00Z",
        quote_content_hash: HASH_A,
      },
    });
    const spy = stubServer({
      "POST /api/v1/trips/t1/booking-intents": () => json(intent(), 201),
      "POST /api/v1/booking-intents/i1/approvals": () => json(approved, 201),
    });
    render(<ServerBooking run={RUN} />);
    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));
    await screen.findByText("Free until 24 hours before");

    fireEvent.click(screen.getByRole("button", { name: "Approve these exact terms" }));

    expect(await screen.findByText("Approved, and nothing is booked")).toBeInTheDocument();
    expect(bodyOf(spy, "POST /api/v1/booking-intents/i1/approvals")).toEqual({ quote_content_hash: HASH_A });
    expect(screen.getByRole("button", { name: "Approve these exact terms" })).toBeDisabled();
    expect(spy.mock.calls.some(([input]) => String(input).includes("/execute"))).toBe(false);
  });

  test("when the terms changed, the new terms are shown and nothing is approved", async () => {
    stubServer({
      "POST /api/v1/trips/t1/booking-intents": () => json(intent(), 201),
      "POST /api/v1/booking-intents/i1/approvals": () =>
        json({ title: "Conflict", detail: "The provider's terms changed; look at the new quote.", code: "quote_changed" }, 409),
      "GET /api/v1/booking-intents/i1": () => json(intent({}, 650000, HASH_B)),
    });
    render(<ServerBooking run={RUN} />);
    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));
    await screen.findByText("Free until 24 hours before");

    fireEvent.click(screen.getByRole("button", { name: "Approve these exact terms" }));

    expect(await screen.findByText("The terms changed")).toBeInTheDocument();
    expect(screen.getByText(/provider's terms changed/)).toBeInTheDocument();
    expect(screen.getByText(HASH_B.slice(0, 12))).toBeInTheDocument();
    expect(screen.queryByText("Approved, and nothing is booked")).not.toBeInTheDocument();
    // The person can look again and decide: approval is offered again, for the new terms only.
    expect(screen.getByRole("button", { name: "Approve these exact terms" })).toBeEnabled();
  });

  test("a quote that cannot be re-checked is reported and not treated as approved", async () => {
    stubServer({
      "POST /api/v1/trips/t1/booking-intents": () => json(intent(), 201),
      "POST /api/v1/booking-intents/i1/approvals": () =>
        json({ title: "Unavailable", detail: "The quote could not be re-checked.", code: "revalidation_failed" }, 503),
    });
    render(<ServerBooking run={RUN} />);
    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));
    await screen.findByText("Free until 24 hours before");

    fireEvent.click(screen.getByRole("button", { name: "Approve these exact terms" }));

    expect(await screen.findByText("The quote could not be re-checked.")).toBeInTheDocument();
    expect(screen.queryByText("Approved, and nothing is booked")).not.toBeInTheDocument();
  });

  test("it renders nothing when nothing was chosen", () => {
    const { container } = render(
      <ServerBooking run={{ ...RUN, selected: { transportId: null, returnTransportId: null, hotelId: null } }} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("the booking client", () => {
  test("refuses an answer that does not say booking is switched off", async () => {
    stubServer({
      "POST /api/v1/trips/t1/booking-intents": () => json(intent({ booking_enabled: true }), 201),
    });

    await expect(createIntent("t1", "TRANSPORT", "a", "key-12345")).rejects.toMatchObject({
      name: "PlanningApiError",
    });
  });

  test("refuses an answer with a malformed fingerprint", async () => {
    stubServer({
      "POST /api/v1/trips/t1/booking-intents": () => json(intent({ quote_content_hash: "short" }), 201),
    });

    await expect(createIntent("t1", "TRANSPORT", "a", "key-12345")).rejects.toMatchObject({
      detail: expect.stringMatching(/expected shape/) as unknown,
    });
  });
});
