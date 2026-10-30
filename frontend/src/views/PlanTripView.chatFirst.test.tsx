import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { PlanTripView } from "./PlanTripView";

const ITINERARY = {
  destination: { name: "Goa" },
  start_date: "2026-11-07",
  days: 5,
  travellers: null,
  preferences: null,
};

const PLAN = {
  source: "SCRIPTED_SAMPLE",
  notice: "Scripted sample: fixed placeholder text, not written by a language model.",
  plan: {
    days: Array.from({ length: 5 }, (_, index) => ({
      day_number: index + 1,
      items: [{ title: `Plan line for day ${index + 1}`, description: null }],
    })),
    notes: null,
  },
};

/** Answers the chat endpoint with `reply` and the plan endpoint with `plan`, like the server. */
function stubServer(reply: Record<string, unknown>, plan: unknown = PLAN, planStatus = 200) {
  const turn = {
    status: "READY_FOR_REVIEW",
    reply: "Here is what I have: a 5-day itinerary for Goa starting 7 November 2026.",
    draft: { destination: "Goa", trip_days: 5 },
    trip_request: null,
    itinerary_request: null,
    changes: [],
    rejections: [],
    model: { kind: "DEV_STAND_IN", notice: "Development stand-in: not a language model." },
    ...reply,
  };
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      new Response(JSON.stringify(url.endsWith("/plans") ? plan : turn), {
        status: url.endsWith("/plans") ? planStatus : 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The voice panel has its own typed-message box and "Send" button, so the chat is addressed by its
// region.
async function ask(message: string) {
  const chat = within(screen.getByRole("region", { name: "Describe your trip in a message" }));
  fireEvent.change(chat.getByLabelText(/for example/i), { target: { value: message } });
  fireEvent.click(chat.getByRole("button", { name: "Send" }));
  await screen.findByText(/Here is what I have/);
}

afterEach(() => vi.unstubAllGlobals());

describe("chat first", () => {
  test("the conversation is the main screen and the search dashboard is not shown", () => {
    render(<PlanTripView chatFirst />);

    expect(screen.getByRole("heading", { level: 1, name: "Where to next?" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Describe your trip in a message" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Use example trip/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview with demo data" })).not.toBeInTheDocument();
  });

  test("chat and voice are both on the screen at once, without opening the comparison", () => {
    render(<PlanTripView chatFirst />);

    expect(screen.getByRole("heading", { name: "Describe your trip in a message" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Talk to TravelMate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to TravelMate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Use example trip/ })).not.toBeInTheDocument();
  });

  test("the voice screen shows once, and opening the comparison does not add a second one", () => {
    render(<PlanTripView chatFirst />);

    fireEvent.click(screen.getByRole("button", { name: "Compare transport and hotels instead" }));

    expect(screen.getAllByRole("heading", { name: "Talk to TravelMate" })).toHaveLength(1);
  });

  test("the voice screen's way back leads to the chat, not to a trip form", () => {
    render(<PlanTripView chatFirst />);

    fireEvent.click(screen.getByRole("button", { name: "Back to the chat" }));

    expect(screen.queryByRole("button", { name: "Back to the trip form" })).not.toBeInTheDocument();
    expect(document.activeElement).toBe(document.querySelector(".assistant-chat"));
  });

  test("the comparison view opens and closes behind a button", () => {
    render(<PlanTripView chatFirst />);
    const toggle = screen.getByRole("button", { name: "Compare transport and hotels instead" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: /Use example trip/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Hide the transport and hotel comparison" }),
    ).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Hide the transport and hotel comparison" }));
    expect(screen.queryByRole("button", { name: /Use example trip/ })).not.toBeInTheDocument();
  });

  test("an itinerary request fetches the server's plan and shows its label, with nothing to book", async () => {
    const fetchMock = stubServer({ itinerary_request: ITINERARY });
    render(<PlanTripView chatFirst />);

    await ask("plan my 5 days itinerary for Goa this weekend");
    expect(screen.queryByRole("heading", { name: "5-day plan for Goa" })).not.toBeInTheDocument();
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.some(([url]) => url.endsWith("/plans"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Show the plan" }));

    expect(await screen.findByText("Plan line for day 1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "5-day plan for Goa" })).toBeInTheDocument();
    expect(screen.getByText(/^Scripted sample ·/)).toBeInTheDocument(); // the banner
    const call = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) =>
      url.endsWith("/plans"),
    );
    expect(JSON.parse(call?.[1].body as string)).toEqual({
      itinerary_request: ITINERARY,
    });
    expect(screen.queryByRole("button", { name: /book|pay|approve/i })).not.toBeInTheDocument();
  });

  test("when the server cannot write the plan, no plan is shown", async () => {
    stubServer(
      { itinerary_request: ITINERARY },
      { title: "Plan unavailable", detail: "The model service is not available right now." },
      503,
    );
    render(<PlanTripView chatFirst />);

    await ask("plan my 5 days itinerary for Goa this weekend");
    fireEvent.click(screen.getByRole("button", { name: "Show the plan" }));

    expect(await screen.findByText(/The plan could not be written/)).toBeInTheDocument();
    expect(screen.queryByText("Plan line for day 1")).not.toBeInTheDocument();
  });

  test("a trip request from the chat opens the comparison view with its results", async () => {
    stubServer({
      trip_request: {
        trip_type: "ONE_WAY",
        origin: { name: "Indore" },
        destination: { name: "Goa" },
        departure_date: "2026-12-12",
        return_date: null,
        travellers: [{ age: null }],
        preferences: null,
      },
    });
    render(<PlanTripView chatFirst />);

    await ask("from Indore to Goa on 12 December, one way, 1 person");
    fireEvent.click(screen.getByRole("button", { name: "Use these details" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Demo results" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Hide the transport and hotel comparison" })).toBeInTheDocument();
  });

  test("without chat first the page is the dashboard, as before", () => {
    render(<PlanTripView />);

    expect(screen.getByRole("heading", { level: 1, name: "Plan your trip" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Describe your trip in a message" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Compare transport and hotels instead" })).not.toBeInTheDocument();
  });
});
