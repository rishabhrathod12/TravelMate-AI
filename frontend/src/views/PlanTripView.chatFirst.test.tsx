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

function stubServer(reply: Record<string, unknown>) {
  const body = {
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
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
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

  test("an itinerary request shows the scripted sample plan, labelled, and nothing to book", async () => {
    stubServer({ itinerary_request: ITINERARY });
    render(<PlanTripView chatFirst />);

    await ask("plan my 5 days itinerary for Goa this weekend");
    expect(screen.queryByRole("heading", { name: "5-day plan for Goa" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show the sample plan" }));

    expect(screen.getByRole("heading", { name: "5-day plan for Goa" })).toBeInTheDocument();
    expect(screen.getByText(/not written by a language model/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /book|pay|approve/i })).not.toBeInTheDocument();
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
