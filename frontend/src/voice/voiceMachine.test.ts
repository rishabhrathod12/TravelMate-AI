import { describe, expect, test } from "vitest";

import {
  initialVoiceState,
  voiceReducer,
  type VoiceEvent,
  type VoiceSessionState,
  type VoiceState,
} from "./voiceMachine";

function run(events: VoiceEvent[], from: VoiceSessionState = initialVoiceState) {
  return events.reduce(voiceReducer, from);
}

const connectVoice: VoiceEvent = { type: "CONNECT", mode: "voice" };
const connectText: VoiceEvent = { type: "CONNECT", mode: "text" };
const connected: VoiceEvent = { type: "CONNECTED" };
const say: VoiceEvent = { type: "TRANSCRIPT", speaker: "user", text: "hello", source: "voice" };
const fail: VoiceEvent = { type: "FAIL", code: "connection", message: "boom" };

const live = [connectVoice, connected];

describe("a normal conversation", () => {
  test("idle, connecting, listening, thinking, speaking, listening", () => {
    expect(run([connectVoice]).status).toBe("connecting");
    expect(run(live).status).toBe("listening");
    expect(run([...live, { type: "PHASE", phase: "thinking" }]).status).toBe("thinking");
    expect(run([...live, { type: "PHASE", phase: "speaking" }]).status).toBe("speaking");
    expect(run([...live, { type: "PHASE", phase: "speaking" }, { type: "PHASE", phase: "listening" }]).status).toBe("listening");
  });

  test("keeps both sides in order with unique ids and trims text", () => {
    const state = run([
      ...live,
      { type: "TRANSCRIPT", speaker: "user", text: "  hi  ", source: "voice" },
      { type: "TRANSCRIPT", speaker: "assistant", text: "hello", source: "assistant" },
    ]);

    expect(state.transcript.map((entry) => [entry.speaker, entry.text, entry.source])).toEqual([
      ["user", "hi", "voice"],
      ["assistant", "hello", "assistant"],
    ]);
    expect(new Set(state.transcript.map((entry) => entry.id)).size).toBe(2);
  });

  test("ignores empty text and text outside a live session", () => {
    const empty: VoiceEvent = { type: "TRANSCRIPT", speaker: "user", text: "  ", source: "typed" };

    expect(run([...live, empty]).transcript).toEqual([]);
    expect(run([say])).toBe(initialVoiceState);
    expect(run([connectVoice, say]).transcript).toEqual([]);
  });

  test("the user can speak while the assistant is speaking (interruption)", () => {
    const state = run([...live, { type: "PHASE", phase: "speaking" }, { type: "PHASE", phase: "listening" }, say]);

    expect(state.status).toBe("listening");
    expect(state.transcript).toHaveLength(1);
  });
});

describe("muting", () => {
  test("toggles in a live voice session and clears on end", () => {
    const muted = run([...live, { type: "SET_MUTED", muted: true }]);

    expect(muted.muted).toBe(true);
    expect(run([{ type: "SET_MUTED", muted: false }], muted).muted).toBe(false);
    expect(run([{ type: "END" }], muted).muted).toBe(false);
  });

  test("does nothing in a text session or before the session is live", () => {
    const text = run([connectText, connected, { type: "SET_MUTED", muted: true }]);

    expect(text.muted).toBe(false);
    expect(run([connectVoice, { type: "SET_MUTED", muted: true }]).muted).toBe(false);
  });
});

describe("errors", () => {
  test("shows the code and message and keeps the transcript", () => {
    const state = run([...live, say, fail]);

    expect(state.status).toBe("error");
    expect(state.error).toEqual({ code: "connection", message: "boom" });
    expect(state.transcript).toHaveLength(1);
  });

  test("a failure can happen while connecting, for example a refused microphone", () => {
    const state = run([connectVoice, { type: "FAIL", code: "permission_denied", message: "no" }]);

    expect(state.status).toBe("error");
    expect(state.error?.code).toBe("permission_denied");
  });

  test("dismissing returns to idle; retrying keeps the transcript and the mode", () => {
    const failed = run([...live, say, fail]);

    expect(run([{ type: "DISMISS_ERROR" }], failed)).toMatchObject({ status: "idle", error: null });
    const retried = run([connectText], failed);
    expect(retried).toMatchObject({ status: "connecting", mode: "text", error: null });
    expect(retried.transcript).toHaveLength(1);
  });

  test("a failure while idle or already failed is ignored", () => {
    expect(run([fail])).toBe(initialVoiceState);
    const failed = run([...live, fail]);
    expect(voiceReducer(failed, { type: "FAIL", code: "unknown", message: "later" })).toBe(failed);
  });
});

describe("ending and restarting", () => {
  test("ending returns to idle and keeps the transcript; a new session clears it", () => {
    const ended = run([...live, say, { type: "END" }]);

    expect(ended.status).toBe("idle");
    expect(ended.transcript).toHaveLength(1);
    expect(run([connectVoice], ended).transcript).toEqual([]);
  });

  test("ending can happen during connecting and after an error", () => {
    expect(run([connectVoice, { type: "END" }]).status).toBe("idle");
    expect(run([connectVoice, fail, { type: "END" }]).status).toBe("idle");
  });
});

describe("events that are not allowed in a state are ignored", () => {
  const events: Record<string, VoiceEvent> = {
    CONNECT: connectVoice,
    CONNECTED: connected,
    PHASE: { type: "PHASE", phase: "thinking" },
    TRANSCRIPT: say,
    SET_MUTED: { type: "SET_MUTED", muted: true },
    DISMISS_ERROR: { type: "DISMISS_ERROR" },
  };

  const ignored: Record<VoiceState, string[]> = {
    idle: ["CONNECTED", "PHASE", "TRANSCRIPT", "SET_MUTED", "DISMISS_ERROR"],
    connecting: ["CONNECT", "PHASE", "TRANSCRIPT", "SET_MUTED", "DISMISS_ERROR"],
    listening: ["CONNECT", "CONNECTED", "DISMISS_ERROR"],
    thinking: ["CONNECT", "CONNECTED", "DISMISS_ERROR"],
    speaking: ["CONNECT", "CONNECTED", "DISMISS_ERROR"],
    error: ["CONNECTED", "PHASE", "TRANSCRIPT", "SET_MUTED"],
  };

  const reach: Record<VoiceState, VoiceEvent[]> = {
    idle: [],
    connecting: [connectVoice],
    listening: live,
    thinking: [...live, { type: "PHASE", phase: "thinking" }],
    speaking: [...live, { type: "PHASE", phase: "speaking" }],
    error: [connectVoice, fail],
  };

  for (const [status, names] of Object.entries(ignored) as [VoiceState, string[]][]) {
    for (const name of names) {
      test(`${name} is ignored while ${status}`, () => {
        const state = run(reach[status]);
        const event = events[name] as VoiceEvent;

        // PHASE to the state it is already in is a valid no-change, so compare by value there.
        expect(voiceReducer(state, event)).toEqual(state);
      });
    }
  }
});
