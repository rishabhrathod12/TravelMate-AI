import { afterEach, describe, expect, test, vi } from "vitest";

import { createMockVoiceAdapter, MOCK_REPLIES, SIMULATED_USER_PHRASE } from "./mockAdapter";
import { VoiceConnectionError, type AdapterEvent } from "./VoiceAdapter";

const fast = { connectMs: 0, thinkMs: 0, speakMs: 0 };

afterEach(() => {
  vi.useRealTimers();
});

describe("the development mock", () => {
  test("says plainly that it is a mock with no audio and nothing to disclose", () => {
    const adapter = createMockVoiceAdapter();

    expect(adapter.isMock).toBe(true);
    expect(adapter.playsAudio).toBe(false);
    expect(adapter.audioDisclosure).toBeNull();
    expect(adapter.devControls).toBeDefined();
  });

  test("replies with the script in order, whatever the user types, then repeats the last", async () => {
    vi.useFakeTimers();
    const adapter = createMockVoiceAdapter({ connectMs: 1, thinkMs: 1, speakMs: 1 });
    const events: AdapterEvent[] = [];
    const connecting = adapter.connect({ microphone: false }, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(5);
    await connecting;

    for (const text of ["a", "b", "c", "d"]) {
      adapter.sendText(text);
      await vi.advanceTimersByTimeAsync(10);
    }

    const replies = events.flatMap((event) =>
      event.type === "transcript" && event.speaker === "assistant" ? [event.text] : [],
    );
    expect(replies).toEqual([...MOCK_REPLIES, MOCK_REPLIES[MOCK_REPLIES.length - 1]]);
    expect(events.at(-1)).toEqual({ type: "listening" });
  });

  test("a simulated phrase is labelled as simulated and is ignored while muted", async () => {
    vi.useFakeTimers();
    const adapter = createMockVoiceAdapter({ connectMs: 1, thinkMs: 1, speakMs: 1 });
    const events: AdapterEvent[] = [];
    const connecting = adapter.connect({ microphone: true }, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(5);
    await connecting;

    adapter.setMuted(true);
    adapter.devControls?.simulateUserPhrase();
    expect(events).toEqual([]);

    adapter.setMuted(false);
    adapter.devControls?.simulateUserPhrase();
    expect(events[0]).toEqual({
      type: "transcript",
      speaker: "user",
      text: SIMULATED_USER_PHRASE,
      source: "simulated",
    });
  });

  test("can refuse the microphone once, as a browser would, but never for a text session", async () => {
    const adapter = createMockVoiceAdapter(fast);
    adapter.devControls?.denyMicrophoneNextTime();

    await expect(adapter.connect({ microphone: true }, () => undefined)).rejects.toMatchObject({
      code: "permission_denied",
    });
    await expect(adapter.connect({ microphone: true }, () => undefined)).resolves.toBeUndefined();
  });

  test("a text session is not affected by a blocked microphone", async () => {
    const adapter = createMockVoiceAdapter(fast);
    adapter.devControls?.denyMicrophoneNextTime();

    await expect(adapter.connect({ microphone: false }, () => undefined)).resolves.toBeUndefined();
  });

  test("fails the reply on the chosen turn only", async () => {
    vi.useFakeTimers();
    const adapter = createMockVoiceAdapter({ connectMs: 1, thinkMs: 1, speakMs: 1, failAtTurn: 0 });
    const events: AdapterEvent[] = [];
    const connecting = adapter.connect({ microphone: false }, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(5);
    await connecting;

    adapter.sendText("a");
    await vi.advanceTimersByTimeAsync(10);

    expect(events.some((event) => event.type === "error")).toBe(true);
  });

  test("interrupting stops the reply and goes back to listening", async () => {
    vi.useFakeTimers();
    const adapter = createMockVoiceAdapter({ connectMs: 1, thinkMs: 1, speakMs: 10_000 });
    const events: AdapterEvent[] = [];
    const connecting = adapter.connect({ microphone: false }, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(5);
    await connecting;
    adapter.sendText("a");
    await vi.advanceTimersByTimeAsync(5);
    expect(events.at(-1)).toEqual({ type: "speaking" });

    adapter.interrupt();
    await vi.advanceTimersByTimeAsync(20_000);

    expect(events.at(-1)).toEqual({ type: "listening" });
    expect(events.filter((event) => event.type === "listening")).toHaveLength(1);
  });

  test("disconnecting while connecting rejects the pending connection", async () => {
    vi.useFakeTimers();
    const adapter = createMockVoiceAdapter({ connectMs: 10_000 });
    const pending = adapter.connect({ microphone: true }, () => undefined);
    const assertion = expect(pending).rejects.toBeInstanceOf(VoiceConnectionError);

    adapter.disconnect();

    await assertion;
  });

  test("never touches the network or the microphone", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", () => {
      calls.push("fetch");
      return Promise.reject(new Error("network used"));
    });
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: () => {
          calls.push("getUserMedia");
          return Promise.reject(new Error("microphone used"));
        },
      },
    });
    const adapter = createMockVoiceAdapter(fast);

    await adapter.connect({ microphone: true }, () => undefined);
    adapter.sendText("a");

    expect(calls).toEqual([]);
  });
});
