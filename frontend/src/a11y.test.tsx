import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { ChatTurn } from "./api/chat";
import type { PlanningRun } from "./api/planning";
import App from "./App";
import { ServerBooking } from "./components/ServerBooking";
import { ServerClarification } from "./components/ServerClarification";
import { ServerItinerary } from "./components/ServerItinerary";
import { createMockVoiceAdapter } from "./voice/mockAdapter";
import { stubHealthOk } from "./test/mockFetch";
import { expectNoViolations } from "./test/axe";
import { HomeView } from "./views/HomeView";

/**
 * Accessibility audit of the core screens with axe-core (plan M11, NFR-12). These are regression
 * tests: they fail when a change introduces a violation. Colour contrast is audited in a real
 * browser instead (see src/test/axe.ts).
 */

beforeEach(() => {
  window.location.hash = "";
  stubHealthOk();
});

afterEach(() => {
  window.location.hash = "";
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const READY_TURN: ChatTurn = {
  status: "READY_FOR_REVIEW",
  reply: "Here is what I have: Indore to Goa, one way, 12 December.",
  draft: {},
  tripRequest: {
    trip_type: "ONE_WAY",
    origin: { name: "Indore" },
    destination: { name: "Goa" },
    departure_date: "2026-12-12",
    return_date: null,
    travellers: [{ age: null }],
    preferences: null,
  },
  itineraryRequest: null,
  modelKind: "DEV_STAND_IN",
  modelNotice: "Development stand-in: not a language model.",
};

describe("the harness", () => {
  test("catches real violations, so a pass means something", async () => {
    const { container } = render(
      <main>
        <img src="x.png" />
        <button type="button" />
        <input type="text" />
      </main>,
    );

    await expect(expectNoViolations(container)).rejects.toThrow(/image-alt|button-name|label/);
  });
});

describe("pages", () => {
  test("home, as the whole page", async () => {
    const { container } = render(<App />);
    await screen.findByText(/Backend: online/);

    await expectNoViolations(container, { page: true });
  });

  test("home with the menu open", async () => {
    const { container } = render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Menu" }));

    await expectNoViolations(container, { page: true });
  });

  test("home in a production build: voice and chat switched off", async () => {
    const { container } = render(<HomeView adapter={null} chatAvailable={false} />);

    await expectNoViolations(container);
  });

  test("My trips and About", async () => {
    for (const hash of ["#/trips", "#/about"]) {
      window.location.hash = hash;
      const { container, unmount } = render(<App />);
      await screen.findByRole("main");

      await expectNoViolations(container, { page: true });
      unmount();
    }
  });

  test("the trip form page, empty", async () => {
    window.location.hash = "#/form";
    const { container } = render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Plan your trip" });

    await expectNoViolations(container, { page: true });
  });

  test("the trip form page with demo results, a selection and the approval preview", async () => {
    window.location.hash = "#/form";
    const { container } = render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Use example trip/ }));
    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));
    await screen.findByRole("heading", { name: "Demo results" });
    fireEvent.click(screen.getAllByRole("button", { name: /^Select/ })[0] as HTMLElement);

    await expectNoViolations(container, { page: true });
  });
});

describe("the conversation", () => {
  test("after a message, with the ready actions", async () => {
    const send = vi.fn().mockResolvedValue(READY_TURN);
    const { container } = render(<HomeView adapter={createMockVoiceAdapter()} chatAvailable send={send} />);
    fireEvent.change(screen.getByLabelText("Message TravelMate"), { target: { value: "Indore to Goa" } });
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });
    await screen.findByText(/Here is what I have/);

    await expectNoViolations(container);
  });

  test("with the comparison view open", async () => {
    const send = vi.fn().mockResolvedValue(READY_TURN);
    const { container } = render(<HomeView adapter={null} chatAvailable send={send} />);
    fireEvent.change(screen.getByLabelText("Message TravelMate"), { target: { value: "Indore to Goa" } });
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });
    fireEvent.click(await screen.findByRole("button", { name: "Use these details" }));
    await screen.findByRole("heading", { name: "Demo results" });

    await expectNoViolations(container);
  });

  test("during a mock voice session", async () => {
    const { container } = render(<HomeView adapter={createMockVoiceAdapter()} chatAvailable />);
    fireEvent.click(screen.getByRole("button", { name: "Talk to TravelMate" }));
    await screen.findByRole("button", { name: "End session" });

    await expectNoViolations(container);
  });
});

describe("the server planner panels", () => {
  const SOURCE = {
    provenance: "MOCK",
    provider_name: "mock-transport",
    retrieved_at: "2026-01-01T00:00:00Z",
    freshness_window_seconds: 900,
  };
  const INTENT = {
    id: "i1",
    trip_id: "t1",
    status: "AWAITING_APPROVAL",
    category: "TRANSPORT",
    quote: {
      id: "q1",
      option_id: "a",
      price: { amount_minor: 500000, currency: "INR" },
      price_basis: "PER_TRAVELLER",
      fees: [{ label: "Convenience fee", amount: { amount_minor: 15000, currency: "INR" } }],
      availability: "AVAILABLE",
      cancellation_terms: "Free until 24 hours before",
      valid_until: "2026-12-01T00:00:00Z",
      source: SOURCE,
    },
    quote_content_hash: "a".repeat(64),
    quote_valid_until: "2026-12-01T00:00:00Z",
    availability: "AVAILABLE",
    price_basis: "PER_TRAVELLER",
    travellers: 1,
    approval: null,
    booking_enabled: false,
    notice: "Booking is switched off.",
    request_id: "r",
  };
  const RUN = {
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
    },
    estimate: null,
    error: null,
    questions: ["How many people are travelling?"],
    selected: { transportId: "a", returnTransportId: null, hotelId: null },
    itinerary: null,
    itineraryWarnings: [],
  } as unknown as PlanningRun;

  afterEach(() => vi.unstubAllGlobals());

  test("the approval step: terms, then approved", async () => {
    const approved = {
      ...INTENT,
      status: "APPROVED",
      approval: {
        id: "ap1",
        approved_at: "2026-11-02T10:00:00Z",
        expires_at: "2026-11-02T10:15:00Z",
        quote_content_hash: "a".repeat(64),
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((input) =>
        Promise.resolve(String(input).endsWith("/approvals") ? json(approved, 201) : json(INTENT, 201)),
      ),
    );
    const { container } = render(<ServerBooking run={RUN} />);
    await expectNoViolations(container);

    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));
    await screen.findByText("Terms fingerprint");
    await expectNoViolations(container);

    fireEvent.click(screen.getByRole("button", { name: "Approve these exact terms" }));
    await screen.findByText("Approved, and nothing is booked");
    await expectNoViolations(container);
  });

  test("the approval step with an error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(() => Promise.resolve(json({ title: "Unavailable", detail: "The quote could not be re-checked." }, 503))),
    );
    const { container } = render(<ServerBooking run={RUN} />);
    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));
    await screen.findByText("The quote could not be re-checked.");

    await expectNoViolations(container);
  });

  test("the itinerary editor", async () => {
    const { container } = render(
      <ServerItinerary
        tripId="t1"
        initial={{
          days: [
            { day_number: 1, items: [{ title: "Travel to Goa", description: null, option_id: "a" }] },
            { day_number: 2, items: [] },
          ],
          notes: null,
        }}
        warnings={["Day 3 was left empty."]}
      />,
    );

    await expectNoViolations(container);
  });

  test("the clarification form", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(() =>
        Promise.resolve(json({ id: "t1", draft: { origin: "Indore", destination: "Goa", departure_date: "2026-12-12" } })),
      ),
    );
    const { container } = render(<ServerClarification run={RUN} onAnswered={() => undefined} />);
    await screen.findByDisplayValue("Indore");

    await expectNoViolations(container);
  });
});
