import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { createMockVoiceAdapter, MOCK_REPLIES, SIMULATED_USER_PHRASE } from "../../voice/mockAdapter";
import {
  VoiceConnectionError,
  type AdapterListener,
  type VoiceAdapter,
} from "../../voice/VoiceAdapter";
import { VoiceMode } from "./VoiceMode";

const fast = { connectMs: 0, thinkMs: 0, speakMs: 0 };
const slowSpeech = { connectMs: 0, thinkMs: 0, speakMs: 10_000 };

const button = (name: RegExp | string) => screen.getByRole("button", { name });
const maybeButton = (name: RegExp | string) => screen.queryByRole("button", { name });
const status = () => screen.getByRole("status");

/** A real-looking adapter (not a mock) whose behaviour each test controls. */
function fakeRealAdapter(overrides: Partial<VoiceAdapter> = {}) {
  let listener: AdapterListener = () => undefined;
  const adapter: VoiceAdapter & { emit: AdapterListener } = {
    name: "Fake realtime",
    isMock: false,
    playsAudio: true,
    audioDisclosure: "Your voice is processed by a third-party voice service.",
    connect: vi.fn((_options, next: AdapterListener) => {
      listener = next;
      return Promise.resolve();
    }),
    disconnect: vi.fn(),
    setMuted: vi.fn(),
    interrupt: vi.fn(),
    sendText: vi.fn(),
    emit: (event) => listener(event),
    ...overrides,
  };
  return adapter;
}

async function startVoice() {
  fireEvent.click(button("Talk to TravelMate"));
  await waitFor(() => expect(status()).toHaveTextContent(/Listening/));
}

describe("when no voice service is available", () => {
  test("says so, disables the button and the text box, and offers no mock controls", () => {
    render(<VoiceMode adapter={null} />);

    expect(screen.getByText("Voice isn't available yet")).toBeInTheDocument();
    expect(button("Talk to TravelMate")).toBeDisabled();
    expect(screen.getByLabelText("Or type a message")).toBeDisabled();
    expect(screen.queryByText(/Mock:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/MOCK/)).not.toBeInTheDocument();
  });
});

describe("the main button and states", () => {
  test("one prominent button starts a voice session: connecting, then listening", async () => {
    render(<VoiceMode adapter={createMockVoiceAdapter({ ...fast, connectMs: 20 })} />);

    expect(screen.getByRole("heading", { name: "Talk to TravelMate" })).toBeInTheDocument();
    fireEvent.click(button("Talk to TravelMate"));
    expect(status()).toHaveTextContent("Connecting");

    await waitFor(() => expect(status()).toHaveTextContent("Listening… go ahead and speak."));
    expect(maybeButton("Talk to TravelMate")).not.toBeInTheDocument();
    expect(button("End session")).toBeEnabled();
  });

  test("asks the adapter for the microphone in a voice session and not in a text session", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);

    await startVoice();
    expect(adapter.connect).toHaveBeenLastCalledWith({ microphone: true }, expect.any(Function));
  });

  test("shows the audio disclosure before the first use", () => {
    render(<VoiceMode adapter={fakeRealAdapter()} />);

    expect(screen.getByText("Your voice is processed by a third-party voice service.")).toBeInTheDocument();
  });

  test("shows thinking and speaking as the adapter reports them, and a transcript", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);
    await startVoice();

    adapter.emit({ type: "transcript", speaker: "user", text: "Goa jana hai", source: "voice" });
    adapter.emit({ type: "thinking" });
    await waitFor(() => expect(status()).toHaveTextContent("Thinking"));
    adapter.emit({ type: "transcript", speaker: "assistant", text: "Kab?", source: "assistant" });
    adapter.emit({ type: "speaking" });

    await waitFor(() => expect(status()).toHaveTextContent("Speaking…"));
    expect(status()).not.toHaveTextContent("no sound");
    const log = screen.getByRole("log", { name: "Transcript" });
    expect(within(log).getAllByRole("listitem")).toHaveLength(2);
  });

  test("the transcript is a collapsible, keyboard-scrollable region", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);
    await startVoice();
    adapter.emit({ type: "transcript", speaker: "user", text: "hi", source: "voice" });

    const log = await screen.findByRole("log", { name: "Transcript" });
    expect(log).toHaveAttribute("tabindex", "0");
    expect(screen.getByText(/Conversation \(1 message\)/).tagName).toBe("SUMMARY");
  });
});

describe("mute, interrupt and end", () => {
  test("mute toggles with aria-pressed and the status says the microphone is off", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);
    await startVoice();

    const mute = button("Mute");
    expect(mute).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(mute);

    expect(adapter.setMuted).toHaveBeenLastCalledWith(true);
    expect(button("Unmute")).toHaveAttribute("aria-pressed", "true");
    expect(status()).toHaveTextContent("Muted");
    fireEvent.click(button("Unmute"));
    expect(adapter.setMuted).toHaveBeenLastCalledWith(false);
  });

  test("Interrupt appears only while the assistant is speaking and calls the adapter", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);
    await startVoice();
    expect(maybeButton("Interrupt")).not.toBeInTheDocument();

    adapter.emit({ type: "speaking" });
    fireEvent.click(await screen.findByRole("button", { name: "Interrupt" }));

    expect(adapter.interrupt).toHaveBeenCalledTimes(1);
    adapter.emit({ type: "listening" });
    await waitFor(() => expect(maybeButton("Interrupt")).not.toBeInTheDocument());
  });

  test("End session closes the adapter, returns to the start state and keeps the transcript", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);
    await startVoice();
    adapter.emit({ type: "transcript", speaker: "user", text: "hi", source: "voice" });
    await screen.findByRole("log", { name: "Transcript" });

    fireEvent.click(button("End session"));

    expect(adapter.disconnect).toHaveBeenCalled();
    expect(button("Talk to TravelMate")).toBeEnabled();
    expect(screen.getByRole("log", { name: "Transcript" })).toBeInTheDocument();
  });

  test("a session can be cancelled while it is connecting, and a late connection is ignored", async () => {
    let finish: () => void = () => undefined;
    const adapter = fakeRealAdapter({
      connect: vi.fn(() => new Promise<void>((resolve) => (finish = resolve))),
    });
    render(<VoiceMode adapter={adapter} />);

    fireEvent.click(button("Talk to TravelMate"));
    expect(status()).toHaveTextContent("Connecting");
    fireEvent.click(button("Cancel"));
    finish();
    await Promise.resolve();

    expect(button("Talk to TravelMate")).toBeEnabled();
    expect(status()).toHaveTextContent("Ready when you are.");
  });
});

describe("microphone and connection problems", () => {
  const refused = () =>
    fakeRealAdapter({
      connect: vi.fn(() =>
        Promise.reject(new VoiceConnectionError("permission_denied", "Permission was refused.")),
      ),
    });

  test("a refused microphone explains how to fix it and offers text chat", async () => {
    render(<VoiceMode adapter={refused()} />);

    fireEvent.click(button("Talk to TravelMate"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Microphone access was blocked");
    expect(alert).toHaveTextContent("Allow microphone access for this site");
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(maybeButton("Talk to TravelMate")).not.toBeInTheDocument();
  });

  test("'Chat by text instead' opens a text-only session without asking for the microphone", async () => {
    const adapter = refused();
    render(<VoiceMode adapter={adapter} />);
    fireEvent.click(button("Talk to TravelMate"));
    await screen.findByRole("alert");

    adapter.connect = vi.fn(() => Promise.resolve());
    fireEvent.click(button("Chat by text instead"));

    await waitFor(() => expect(status()).toHaveTextContent("Ready. Type your message."));
    expect(adapter.connect).toHaveBeenCalledWith({ microphone: false }, expect.any(Function));
    expect(maybeButton("Mute")).not.toBeInTheDocument();
  });

  test("Dismiss returns to the start state", async () => {
    render(<VoiceMode adapter={refused()} />);
    fireEvent.click(button("Talk to TravelMate"));
    await screen.findByRole("alert");

    fireEvent.click(button("Dismiss"));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(button("Talk to TravelMate")).toBeEnabled();
  });

  test("a connection that drops mid-conversation shows an error and keeps the transcript", async () => {
    const adapter = fakeRealAdapter();
    render(<VoiceMode adapter={adapter} />);
    await startVoice();
    adapter.emit({ type: "transcript", speaker: "user", text: "hi", source: "voice" });

    adapter.emit({ type: "error", code: "connection", message: "Lost it." });

    expect(await screen.findByRole("alert")).toHaveTextContent("The voice connection was lost");
    expect(screen.getByRole("log", { name: "Transcript" })).toBeInTheDocument();
  });
});

describe("text chat", () => {
  test("sending a message with no session opens a text-only session and shows the reply", async () => {
    render(<VoiceMode adapter={createMockVoiceAdapter(fast)} />);

    fireEvent.change(screen.getByLabelText("Or type a message"), { target: { value: "Goa trip" } });
    fireEvent.click(button("Send"));

    const log = await screen.findByRole("log", { name: "Transcript" });
    await waitFor(() => expect(within(log).getAllByRole("listitem")).toHaveLength(2));
    const [mine, theirs] = within(log).getAllByRole("listitem");
    expect(mine).toHaveTextContent("Goa trip");
    expect(mine).toHaveTextContent("typed");
    expect(theirs).toHaveTextContent(MOCK_REPLIES[0] as string);
    expect(theirs).toHaveTextContent("MOCK reply");
    expect(screen.getByLabelText("Or type a message")).toHaveValue("");
  });

  test("cannot send an empty message", () => {
    render(<VoiceMode adapter={createMockVoiceAdapter(fast)} />);

    expect(button("Send")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Or type a message"), { target: { value: "   " } });
    expect(button("Send")).toBeDisabled();
  });
});

describe("the labelled development mock", () => {
  test("is clearly marked and says nothing is heard or played", () => {
    render(<VoiceMode adapter={createMockVoiceAdapter(fast)} />);

    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("MOCK voice (development build)");
    expect(note).toHaveTextContent("No microphone is used and no sound is played or recorded");
  });

  test("the simulation controls live in a separate, labelled developer section", () => {
    render(<VoiceMode adapter={createMockVoiceAdapter(fast)} />);

    const dev = screen.getByText("Developer mock controls (development build only)").closest("details");
    expect(dev).not.toBeNull();
    expect(within(dev as HTMLElement).getAllByRole("button", { hidden: true })).toHaveLength(3);
    // Nothing in the main experience is a simulation control.
    expect(screen.queryByRole("button", { name: /Simulate/ })).not.toBeInTheDocument();
  });

  test("a mock user phrase and reply appear with honest labels, and Interrupt works", async () => {
    render(<VoiceMode adapter={createMockVoiceAdapter(slowSpeech)} />);
    await startVoice();

    fireEvent.click(screen.getByRole("button", { name: "Mock: user says a phrase", hidden: true }));
    await waitFor(() => expect(status()).toHaveTextContent("Speaking… (text only, no sound)"));

    const log = screen.getByRole("log", { name: "Transcript" });
    const [said, replied] = within(log).getAllByRole("listitem");
    expect(said).toHaveTextContent(SIMULATED_USER_PHRASE);
    expect(said).toHaveTextContent("simulated, not heard");
    expect(replied).toHaveTextContent("MOCK reply");

    fireEvent.click(button("Interrupt"));
    await waitFor(() => expect(status()).toHaveTextContent("Listening"));
  });

  test("the mock can simulate a blocked microphone", async () => {
    render(<VoiceMode adapter={createMockVoiceAdapter(fast)} />);

    fireEvent.click(screen.getByRole("button", { name: "Mock: block the microphone next time", hidden: true }));
    fireEvent.click(button("Talk to TravelMate"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Microphone access was blocked");
  });
});

describe("returning to the trip planner", () => {
  test("offers a button that calls the handler", () => {
    const onReturn = vi.fn();
    render(<VoiceMode adapter={null} onReturnToPlanner={onReturn} />);

    fireEvent.click(button("Back to the trip form"));

    expect(onReturn).toHaveBeenCalledTimes(1);
  });
});
