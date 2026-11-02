import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { ChatTurn } from "../api/chat";
import type { TripRequest } from "../contracts/types";
import {
  AWAITING_SELECTION,
  AWAITING_SELECTION_ONE_WAY,
  COMPLETED,
  COMPLETED_ONE_WAY,
  INTENT,
  ONE_WAY,
  ROUND_TRIP,
  RUNNING,
  json,
  stubPlanningServer,
} from "../test/planningFixtures";
import { HomeView } from "./HomeView";

afterEach(() => vi.unstubAllGlobals());

const WAIT = { timeout: 6000 };

function readyTurn(request: TripRequest): ChatTurn {
  return {
    status: "READY_FOR_REVIEW",
    reply: "Here is what I have. Is this right?",
    draft: {},
    tripRequest: request,
    itineraryRequest: null,
    modelKind: "DEV_STAND_IN",
    modelNotice: "Development stand-in: not a language model.",
  };
}

const APPROVED = {
  ...INTENT,
  status: "APPROVED",
  approval: {
    id: "ap1",
    approved_at: "2026-11-02T10:00:00Z",
    expires_at: "2026-11-02T10:15:00Z",
    quote_content_hash: "a".repeat(64),
  },
};

const PLANNING_ROUTES = {
  "POST /api/v1/trips": () => json({ id: "t1" }, 201),
  "POST /api/v1/trips/t1/runs": () => json(RUNNING, 202),
  "GET /api/v1/runs/r1": () => json(AWAITING_SELECTION),
  "POST /api/v1/runs/r1/selections": () => json(COMPLETED, 202),
  "POST /api/v1/trips/t1/booking-intents": () => json(INTENT, 201),
  "POST /api/v1/booking-intents/i1/approvals": () => json(APPROVED, 201),
};

function say(message: string) {
  fireEvent.change(screen.getByLabelText("Message TravelMate"), { target: { value: message } });
  fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });
}

async function openPlanning(request: TripRequest) {
  const send = vi.fn().mockResolvedValue(readyTurn(request));
  render(<HomeView adapter={null} chatAvailable send={send} />);
  say("Indore to Goa");
  fireEvent.click(await screen.findByRole("button", { name: "Plan this trip" }));
  return send;
}

describe("planning a trip from the conversation", () => {
  test("a ready trip offers 'Plan this trip', and nothing starts until the reader presses it", async () => {
    const server = stubPlanningServer(PLANNING_ROUTES);
    const send = vi.fn().mockResolvedValue(readyTurn(ROUND_TRIP));
    render(<HomeView adapter={null} chatAvailable send={send} />);

    say("Indore to Goa");

    expect(await screen.findByRole("button", { name: "Plan this trip" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Use these details" })).toBeInTheDocument(); // the old page is still there
    expect(server.spy).not.toHaveBeenCalled();
  });

  test("the whole journey: rooms, options, choice, estimate, weather, itinerary and the approval step", async () => {
    const server = stubPlanningServer(PLANNING_ROUTES);
    const send = await openPlanning(ROUND_TRIP);

    // 1. The assistant asks for the rooms. It starts nothing until it has a clear answer.
    expect(await screen.findByText(/How many rooms do you need/)).toBeInTheDocument();
    expect(server.spy).not.toHaveBeenCalled();
    say("banana");
    expect(await screen.findByText(/I need a number of rooms from 1 to 9/)).toBeInTheDocument();
    expect(server.spy).not.toHaveBeenCalled();
    say("2 rooms");

    // 2. The planner researches; the options and the weather come back into the conversation.
    expect(await screen.findByRole("heading", { level: 3, name: "Choose your options" }, WAIT)).toBeInTheDocument();
    expect((server.bodyOf("POST /api/v1/trips") as { rooms: number }).rooms).toBe(2);
    expect(screen.getByRole("heading", { level: 3, name: "Weather in Goa" })).toBeInTheDocument();
    expect(screen.getByText(/No forecast for:/)).toBeInTheDocument(); // the horizon is reported, not filled in
    expect(screen.getByRole("heading", { level: 2, name: "Trip planning" })).toBeInTheDocument();
    expect(screen.getAllByText(/MOCK · demo data/).length).toBeGreaterThan(2);

    // 3. A choice. Nothing is sent until the reader presses the button.
    fireEvent.click(screen.getByRole("radio", { name: /FakeAir F1/ }));
    fireEvent.click(screen.getByRole("radio", { name: /FakeAir F2/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Sea View/ }));
    expect(server.keys()).not.toContain("POST /api/v1/runs/r1/selections");
    fireEvent.click(screen.getByRole("button", { name: "Use these choices" }));

    // 4. The result: estimate, weather, itinerary, and the approval step.
    expect(await screen.findByRole("heading", { level: 3, name: /Cost estimate/ })).toBeInTheDocument();
    expect(server.bodyOf("POST /api/v1/runs/r1/selections")).toEqual({
      transport_id: "a",
      return_transport_id: "b",
      hotel_id: "h1",
    });
    expect(screen.getByText("Hotel")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Weather in Goa" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Itinerary draft (not verified)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Approval step (nothing is booked)" })).toBeInTheDocument();
    expect(screen.getByText(/Your plan is ready/)).toBeInTheDocument();

    // 5. The rooms answer was an answer, not a chat message: the chat was asked only once.
    expect(send).toHaveBeenCalledTimes(1);
  }, 30000);

  test("a one-way trip has no hotel stay: no question about rooms, and it plans at once", async () => {
    const server = stubPlanningServer(PLANNING_ROUTES);

    await openPlanning(ONE_WAY);

    expect(await screen.findByText(/no hotel stay/)).toBeInTheDocument();
    expect(screen.queryByText(/How many rooms/)).not.toBeInTheDocument();
    await waitFor(() => expect(server.keys()).toContain("POST /api/v1/trips/t1/runs"));
    expect((server.bodyOf("POST /api/v1/trips") as { rooms: number | null }).rooms).toBeNull();
  });

  test("approval is only ever the reader's own click, and nothing can book", async () => {
    const server = stubPlanningServer({
      ...PLANNING_ROUTES,
      "GET /api/v1/runs/r1": () => json(AWAITING_SELECTION_ONE_WAY),
      "POST /api/v1/runs/r1/selections": () => json(COMPLETED_ONE_WAY, 202),
    });
    await openPlanning(ONE_WAY);
    fireEvent.click(await screen.findByRole("radio", { name: /FakeAir F1/ }, WAIT));
    fireEvent.click(screen.getByRole("button", { name: "Use these choices" }));
    await screen.findByRole("heading", { name: "Approval step (nothing is booked)" });

    // The plan is complete. Without a click, no booking-intent or approval request was made.
    expect(server.keys().some((key) => /booking-intents|approvals|execute/.test(key))).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Get the terms to approve" }));
    await screen.findByText("Terms fingerprint");
    expect(server.keys()).toContain("POST /api/v1/trips/t1/booking-intents");
    expect(server.keys().some((key) => /approvals|execute/.test(key))).toBe(false);
    expect(screen.getByRole("button", { name: "Book (switched off)" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Approve these exact terms" }));
    expect(await screen.findByText("Approved, and nothing is booked")).toBeInTheDocument();
    expect(server.keys()).toContain("POST /api/v1/booking-intents/i1/approvals");
    expect(server.keys().some((key) => /execute/.test(key))).toBe(false);
    expect(screen.getByRole("button", { name: "Book (switched off)" })).toBeDisabled();
  }, 30000);

  test("Stop ends the waiting and the conversation carries on", async () => {
    stubPlanningServer({ ...PLANNING_ROUTES, "GET /api/v1/runs/r1": () => json(RUNNING) });
    await openPlanning(ONE_WAY);
    const panel = within(await screen.findByRole("region", { name: "Trip planning" }));
    await panel.findByText("Researching transport, hotels and weather…");

    fireEvent.click(panel.getByRole("button", { name: "Stop" }));

    expect(await panel.findByText("You stopped waiting")).toBeInTheDocument();
    expect(screen.getByText(/I've stopped waiting for the plan/)).toBeInTheDocument();
    expect(screen.getByLabelText("Message TravelMate")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Plan this trip" })).toBeEnabled();
  });

  test("a server that cannot be reached is reported, and the reader can try again", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await openPlanning(ONE_WAY);

    expect(await screen.findByText("The planning server did not complete this")).toBeInTheDocument();
    expect(screen.getByText(/could not be reached/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Plan this trip" })).toBeEnabled();
  });

  test("the chat still works while a plan is on screen, and the plan is not wiped by it", async () => {
    stubPlanningServer(PLANNING_ROUTES);
    const send = await openPlanning(ONE_WAY);
    await screen.findByRole("heading", { level: 3, name: "Choose your options" }, WAIT);
    send.mockResolvedValueOnce({ ...readyTurn(ONE_WAY), status: "NOT_UNDERSTOOD", tripRequest: null, reply: "Sorry, I did not get that." });

    say("what's the weather like?");

    expect(await screen.findByText("Sorry, I did not get that.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Choose your options" })).toBeInTheDocument();
  });
});
