import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { ChatTurn } from "../api/chat";
import { createMockVoiceAdapter } from "../voice/mockAdapter";
import { HomeView } from "./HomeView";

function turn(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    status: "NEEDS_INFO",
    reply: "Which dates would you like to travel?",
    draft: { destination: "Goa" },
    tripRequest: null,
    itineraryRequest: null,
    modelKind: "DEV_STAND_IN",
    modelNotice: "Development stand-in: not a language model.",
    ...overrides,
  };
}

function type(value: string) {
  fireEvent.change(screen.getByLabelText("Message TravelMate"), { target: { value } });
}

afterEach(() => vi.unstubAllGlobals());

describe("the home screen", () => {
  test("shows only the heading, the voice button and the message box", () => {
    render(<HomeView adapter={createMockVoiceAdapter()} chatAvailable />);

    expect(screen.getByRole("heading", { level: 1, name: "Where do you want to go?" })).toBeInTheDocument();
    expect(screen.getByText("Your personal AI travel planner.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to TravelMate" })).toBeEnabled();
    expect(screen.getByText("Tap to start a voice conversation")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask anything about your trip...")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Conversation" })).not.toBeInTheDocument();
    // None of the dashboard is on the home screen.
    expect(screen.queryByRole("heading", { name: /transport|hotel|weather|budget|itinerary/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /example trip|preview/i })).not.toBeInTheDocument();
  });

  test("a mock voice adapter is labelled as a mock on the button", () => {
    render(<HomeView adapter={createMockVoiceAdapter()} chatAvailable />);

    expect(screen.getByRole("note")).toHaveTextContent(/MOCK voice/);
  });

  test("Enter sends, Shift+Enter does not, and the conversation appears only then", async () => {
    const send = vi.fn().mockResolvedValue(turn());
    render(<HomeView adapter={null} chatAvailable send={send} />);
    const box = screen.getByLabelText("Message TravelMate");
    type("I want to go to Goa this weekend. Plan my trip.");

    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(send).not.toHaveBeenCalled();
    expect(screen.queryByRole("list", { name: "Conversation" })).not.toBeInTheDocument();

    fireEvent.keyDown(box, { key: "Enter" });

    expect(await screen.findByText("Which dates would you like to travel?")).toBeInTheDocument();
    expect(send).toHaveBeenCalledWith("I want to go to Goa this weekend. Plan my trip.", null, expect.any(AbortSignal));
    expect(screen.getByText("I want to go to Goa this weekend. Plan my trip.")).toBeInTheDocument();
    // The visible home heading is replaced, and the page keeps exactly one level-one heading.
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Conversation with TravelMate" })).toBeInTheDocument();
    expect(screen.queryByText("Where do you want to go?")).not.toBeInTheDocument();
    expect((screen.getByLabelText("Message TravelMate") as HTMLTextAreaElement).value).toBe("");
  });

  test("the send button sends, and is off for an empty message", async () => {
    const send = vi.fn().mockResolvedValue(turn());
    render(<HomeView adapter={null} chatAvailable send={send} />);
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();

    type("  ");
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    type("Goa");
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("Which dates would you like to travel?");
    expect(send).toHaveBeenCalledTimes(1);
  });

  test("the draft from one answer is sent back with the next message", async () => {
    const send = vi
      .fn()
      .mockResolvedValueOnce(turn())
      .mockResolvedValueOnce(turn({ reply: "And how many people?" }));
    render(<HomeView adapter={null} chatAvailable send={send} />);

    type("Goa");
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });
    await screen.findByText("Which dates would you like to travel?");
    type("12 December");
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });

    await screen.findByText("And how many people?");
    expect(send.mock.calls[1]?.[1]).toEqual({ destination: "Goa" });
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(4);
  });

  test("a failed message shows an error and no invented answer", async () => {
    const send = vi.fn().mockRejectedValue(new Error("boom"));
    render(<HomeView adapter={null} chatAvailable send={send} />);

    type("Goa");
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });

    expect(await screen.findByRole("alert")).toHaveTextContent(/Something went wrong/);
  });

  test("the voice button starts the existing voice session and opens the conversation view", async () => {
    render(<HomeView adapter={createMockVoiceAdapter()} chatAvailable />);

    fireEvent.click(screen.getByRole("button", { name: "Talk to TravelMate" }));

    // The shared voice panel appears, still labelled as a mock.
    expect(await screen.findByRole("heading", { name: "Talk to TravelMate" })).toBeInTheDocument();
    expect(screen.getByText(/MOCK voice \(development build\)\./)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "End session" })).toBeInTheDocument());
    // Only one message box: the voice panel's own typed input is hidden.
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.queryByLabelText("Or type a message")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start a voice conversation" })).toBeDisabled();
  });

  test("a trip request from the chat opens the comparison only when asked", async () => {
    const send = vi.fn().mockResolvedValue(
      turn({
        status: "READY_FOR_REVIEW",
        reply: "Here is what I have.",
        tripRequest: {
          trip_type: "ONE_WAY",
          origin: { name: "Indore" },
          destination: { name: "Goa" },
          departure_date: "2026-12-12",
          return_date: null,
          travellers: [{ age: null }],
          preferences: null,
        },
      }),
    );
    render(<HomeView adapter={null} chatAvailable send={send} />);

    type("Indore to Goa on 12 December, one way, 1 person");
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });
    await screen.findByText("Here is what I have.");
    expect(screen.queryByRole("heading", { name: "Demo results" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Use these details" }));

    expect(await screen.findByRole("heading", { name: "Demo results" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(book|pay)/i })).not.toBeInTheDocument();
  });
});

describe("the home screen in production (no voice, no chat)", () => {
  test("says plainly that voice and chat are not available, and sends nothing", () => {
    const send = vi.fn();
    render(<HomeView adapter={null} chatAvailable={false} send={send} />);

    expect(screen.getByRole("button", { name: "Talk to TravelMate" })).toBeDisabled();
    expect(screen.getByText("Voice isn't available yet in this version.")).toBeInTheDocument();
    expect(screen.getByLabelText("Message TravelMate")).toBeDisabled();
    expect(screen.getByText("Chat isn't available yet in this version.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(send).not.toHaveBeenCalled();
  });
});


describe("replies shown progressively", () => {
  const FIRST = "Which dates would you like to travel, and how many people are going on this trip?";
  const SECOND = "Thanks. And where would you like to start from?";

  function say(message: string) {
    type(message);
    fireEvent.keyDown(screen.getByLabelText("Message TravelMate"), { key: "Enter" });
  }

  test("says plainly that the browser shows each reply progressively and the server sends it whole", async () => {
    const send = vi.fn().mockResolvedValue(turn({ reply: FIRST }));
    render(<HomeView adapter={null} chatAvailable send={send} />);

    say("Goa");

    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(
      "Replies are shown progressively by your browser; the server sends each one whole.",
    );
  });

  test("a reply is revealed, can be shown at once, and appears exactly once", async () => {
    const send = vi.fn().mockResolvedValue(turn({ reply: FIRST }));
    render(<HomeView adapter={null} chatAvailable send={send} />);
    say("Goa");

    fireEvent.click(await screen.findByRole("button", { name: "Show the whole reply" }));

    expect(screen.getAllByText(FIRST)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Show the whole reply" })).not.toBeInTheDocument();
    expect(document.querySelectorAll(".message-assistant")).toHaveLength(1);
  });

  test("writing again while a reply is still being revealed completes it, and only the new reply is revealed", async () => {
    const send = vi
      .fn()
      .mockResolvedValueOnce(turn({ reply: FIRST }))
      .mockResolvedValueOnce(turn({ reply: SECOND }));
    render(<HomeView adapter={null} chatAvailable send={send} />);
    say("Goa");
    await screen.findByRole("button", { name: "Show the whole reply" }); // the first reply is mid-reveal

    say("12 December");

    await waitFor(() => expect(document.querySelectorAll(".message-assistant")).toHaveLength(2));
    expect(screen.getAllByText(FIRST)).toHaveLength(1); // whole, and not twice
    expect(screen.getAllByRole("button", { name: "Show the whole reply" })).toHaveLength(1); // only the new reply
  });

  test("shows a thinking indicator with a Stop button while waiting, and Stop leaves the composer usable", async () => {
    const send = vi
      .fn()
      .mockImplementationOnce(
        (_message: string, _draft: unknown, signal?: AbortSignal) =>
          new Promise((_resolve, reject) => {
            signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      )
      .mockResolvedValue(turn({ reply: SECOND }));
    render(<HomeView adapter={null} chatAvailable send={send} />);

    say("Goa");
    expect(await screen.findByText(/TravelMate is thinking/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));

    expect(await screen.findByText(/You stopped this reply/)).toBeInTheDocument();
    expect(screen.queryByText(/TravelMate is thinking/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // stopping is not an error
    expect(document.querySelectorAll(".message-assistant")).toHaveLength(0); // nothing was invented

    say("Goa again");
    fireEvent.click(await screen.findByRole("button", { name: "Show the whole reply" }));
    expect(await screen.findByText(SECOND)).toBeInTheDocument();
    expect(screen.queryByText(/You stopped this reply/)).not.toBeInTheDocument();
  });

  test("an error shows the error line, not a half reply", async () => {
    const send = vi.fn().mockRejectedValue(new Error("boom"));
    render(<HomeView adapter={null} chatAvailable send={send} />);

    say("Goa");

    expect(await screen.findByRole("alert")).toHaveTextContent(/Something went wrong/);
    expect(document.querySelectorAll(".message-assistant")).toHaveLength(0);
    expect(screen.queryByText(/TravelMate is thinking/)).not.toBeInTheDocument();
  });

  test("a Markdown reply becomes real headings, lists, code and links once shown", async () => {
    const reply = [
      "## Plan",
      "",
      "- Day 1: **beach**",
      "- Day 2: [guide](https://example.com/guide)",
      "",
      "```",
      "npm test",
      "```",
    ].join("\n");
    const send = vi.fn().mockResolvedValue(turn({ reply }));
    render(<HomeView adapter={null} chatAvailable send={send} />);
    say("Goa");

    fireEvent.click(await screen.findByRole("button", { name: "Show the whole reply" }));

    expect(screen.getByRole("heading", { level: 2, name: "Plan" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").some((item) => item.textContent === "Day 1: beach")).toBe(true);
    expect(screen.getByRole("link", { name: "guide" })).toHaveAttribute("href", "https://example.com/guide");
    expect(document.querySelector("pre code")?.textContent).toBe("npm test");
  });

  test("raw HTML and script links in a reply are shown as text, never run", async () => {
    const reply = '<img src=x onerror="alert(1)"> [click](javascript:alert(1))';
    const send = vi.fn().mockResolvedValue(turn({ reply }));
    render(<HomeView adapter={null} chatAvailable send={send} />);
    say("Goa");

    fireEvent.click(await screen.findByRole("button", { name: "Show the whole reply" }));

    expect(document.querySelector(".message-assistant img")).toBeNull();
    expect(document.querySelector(".message-assistant a")).toBeNull();
    expect(document.querySelector(".message-assistant")?.textContent).toContain("<img src=x");
  });
});
