import { describe, expect, test } from "vitest";

import { createMockVoiceAdapter, MOCK_REPLIES } from "./mockAdapter";
import { VoiceAbortedError } from "./VoiceAdapter";

const signal = () => new AbortController().signal;

describe("mock voice adapter", () => {
  test("says plainly that it is a mock that plays no audio", () => {
    const adapter = createMockVoiceAdapter();

    expect(adapter.isMock).toBe(true);
    expect(adapter.playsAudio).toBe(false);
  });

  test("gives the scripted replies in order, whatever the user says, then repeats the last", async () => {
    const adapter = createMockVoiceAdapter({ thinkMs: 0 });

    const replies = [];
    for (const said of ["a", "b", "c", "d"]) {
      replies.push(await adapter.respond(said, signal()));
    }

    expect(replies).toEqual([...MOCK_REPLIES, MOCK_REPLIES[MOCK_REPLIES.length - 1]]);
  });

  test("fails on the chosen turn only", async () => {
    const adapter = createMockVoiceAdapter({ thinkMs: 0, failAtTurn: 1 });

    await expect(adapter.respond("a", signal())).resolves.toBe(MOCK_REPLIES[0]);
    await expect(adapter.respond("b", signal())).rejects.toThrow("Mock voice failure");
    await expect(adapter.respond("c", signal())).resolves.toBe(MOCK_REPLIES[2]);
  });

  test("stops waiting when aborted", async () => {
    const adapter = createMockVoiceAdapter({ thinkMs: 10_000, speakMs: 10_000 });
    const controller = new AbortController();

    const pending = adapter.respond("a", controller.signal);
    controller.abort();

    await expect(pending).rejects.toBeInstanceOf(VoiceAbortedError);
    await expect(adapter.speak("x", controller.signal)).rejects.toBeInstanceOf(VoiceAbortedError);
  });

  test("does not read the network", () => {
    // A mock must stay offline: fetch is replaced by a function that fails the test if called.
    const original = globalThis.fetch;
    globalThis.fetch = (() => {
      throw new Error("network used");
    }) as typeof fetch;
    try {
      const adapter = createMockVoiceAdapter({ thinkMs: 0, speakMs: 0 });
      return adapter.respond("a", signal()).then((reply) => adapter.speak(reply, signal()));
    } finally {
      globalThis.fetch = original;
    }
  });
});
