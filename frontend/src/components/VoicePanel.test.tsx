import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { createMockVoiceAdapter, MOCK_REPLIES, SIMULATED_USER_PHRASE } from "../voice/mockAdapter";
import type { VoiceAdapter } from "../voice/VoiceAdapter";
import { VoicePanel } from "./VoicePanel";

function setup(adapter: VoiceAdapter = createMockVoiceAdapter({ thinkMs: 0, speakMs: 0 })) {
  render(<VoicePanel adapter={adapter} />);
}

const button = (name: RegExp | string) => screen.getByRole("button", { name });
const status = () => screen.getByText(/Status:/).closest("p") as HTMLElement;

async function entriesWhenCount(count: number): Promise<HTMLElement[]> {
  await waitFor(() => {
    const list = screen.getByRole("list", { name: "Transcript" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(count);
  });
  return within(screen.getByRole("list", { name: "Transcript" })).getAllByRole("listitem");
}

describe("honesty about mock mode", () => {
  test("states that nothing is heard, played, recorded or understood", () => {
    setup();

    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("MOCK voice");
    expect(note).toHaveTextContent("No microphone is used and no audio is played or recorded");
    expect(note).toHaveTextContent("nothing you say or type is understood");
    expect(screen.getByRole("heading", { name: "Voice assistant (mock)" })).toBeInTheDocument();
  });

  test("never asks for the microphone", () => {
    const calls: string[] = [];
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: () => {
          calls.push("getUserMedia");
          return Promise.reject(new Error("microphone requested"));
        },
      },
    });
    setup();

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate a spoken phrase"));

    expect(calls).toEqual([]);
  });
});

describe("states and controls", () => {
  test("starts idle with only Start enabled", () => {
    setup();

    expect(status()).toHaveTextContent("Idle");
    expect(button("Start session")).toBeEnabled();
    expect(button("Simulate a spoken phrase")).toBeDisabled();
    expect(button("Interrupt")).toBeDisabled();
    expect(button("Resume listening")).toBeDisabled();
    expect(button("Simulate an error")).toBeDisabled();
  });

  test("a session listens, then a simulated phrase gets a MOCK-labelled reply", async () => {
    setup();

    fireEvent.click(button("Start session"));
    expect(status()).toHaveTextContent("Listening");

    fireEvent.click(button("Simulate a spoken phrase"));
    const entries = await entriesWhenCount(2);

    expect(entries[0]).toHaveTextContent(SIMULATED_USER_PHRASE);
    expect(entries[0]).toHaveTextContent("simulated, not heard");
    expect(entries[1]).toHaveTextContent(MOCK_REPLIES[0] as string);
    expect(entries[1]).toHaveTextContent("MOCK reply");
    await waitFor(() => expect(status()).toHaveTextContent("Listening"));
  });

  test("can be interrupted while the assistant is working, then resumed", () => {
    setup(createMockVoiceAdapter({ thinkMs: 10_000 }));

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate a spoken phrase"));
    expect(status()).toHaveTextContent("Thinking");

    fireEvent.click(button("Interrupt"));
    expect(status()).toHaveTextContent("Interrupted");
    expect(button("Resume listening")).toBeEnabled();

    fireEvent.click(button("Resume listening"));
    expect(status()).toHaveTextContent("Listening");
  });

  test("says there is no sound while the mock is speaking", async () => {
    setup(createMockVoiceAdapter({ thinkMs: 0, speakMs: 10_000 }));

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate a spoken phrase"));

    expect(await screen.findByText(/text only, no sound/)).toBeInTheDocument();
  });

  test("ending the session returns to idle but keeps the transcript", async () => {
    setup(createMockVoiceAdapter({ thinkMs: 0, speakMs: 10_000 }));

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate a spoken phrase"));
    await screen.findByText(/text only, no sound/);

    fireEvent.click(button("End session"));

    expect(status()).toHaveTextContent("Idle");
    expect(screen.getByRole("list", { name: "Transcript" })).toBeInTheDocument();
  });
});

describe("errors", () => {
  test("shows an alert with a way out, and a failed reply does not hide the transcript", async () => {
    setup(createMockVoiceAdapter({ thinkMs: 0, failAtTurn: 0 }));

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate a spoken phrase"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not answer");
    expect(status()).toHaveTextContent("Error");
    expect(screen.getByRole("list", { name: "Transcript" })).toBeInTheDocument();

    fireEvent.click(within(alert).getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(status()).toHaveTextContent("Idle");
  });

  test("the simulated error button raises the same alert", () => {
    setup();

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate an error"));

    expect(screen.getByRole("alert")).toHaveTextContent("Simulated error");
  });
});

describe("text fallback", () => {
  test("works without starting a session and shows both sides", async () => {
    setup();

    fireEvent.change(screen.getByLabelText("Type a message instead"), {
      target: { value: "Goa trip" },
    });
    fireEvent.click(button("Send"));

    const entries = await entriesWhenCount(2);
    expect(entries[0]).toHaveTextContent("Goa trip");
    expect(entries[0]).toHaveTextContent("typed");
    expect(entries[1]).toHaveTextContent("MOCK reply");
    expect(screen.getByLabelText("Type a message instead")).toHaveValue("");
  });

  test("does not send an empty message", () => {
    setup();

    expect(button("Send")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Type a message instead"), { target: { value: "  " } });
    expect(button("Send")).toBeDisabled();
  });

  test("is unavailable while the assistant is answering", () => {
    setup(createMockVoiceAdapter({ thinkMs: 10_000 }));

    fireEvent.click(button("Start session"));
    fireEvent.click(button("Simulate a spoken phrase"));

    expect(screen.getByLabelText("Type a message instead")).toBeDisabled();
  });
});
