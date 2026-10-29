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

const user: VoiceEvent = { type: "USER_TEXT", text: "hello", source: "typed" };
const reply: VoiceEvent = { type: "ASSISTANT_TEXT", text: "hi" };

describe("normal conversation", () => {
  test("idle to listening to thinking to speaking and back to listening", () => {
    expect(run([{ type: "START" }]).status).toBe("listening");
    expect(run([{ type: "START" }, user]).status).toBe("thinking");
    expect(run([{ type: "START" }, user, reply]).status).toBe("speaking");
    expect(run([{ type: "START" }, user, reply, { type: "SPEAK_DONE" }]).status).toBe("listening");
  });

  test("keeps both sides of the conversation in order with unique ids", () => {
    const state = run([{ type: "START" }, user, reply]);

    expect(state.transcript.map((entry) => [entry.speaker, entry.text, entry.source])).toEqual([
      ["user", "hello", "typed"],
      ["assistant", "hi", "mock-reply"],
    ]);
    expect(new Set(state.transcript.map((entry) => entry.id)).size).toBe(2);
  });

  test("trims typed text and ignores empty text", () => {
    const listening = run([{ type: "START" }]);

    expect(run([{ type: "USER_TEXT", text: "  hi  ", source: "typed" }], listening).transcript[0]?.text).toBe("hi");
    expect(run([{ type: "USER_TEXT", text: "   ", source: "typed" }], listening)).toBe(listening);
  });
});

describe("interruption", () => {
  test("can interrupt while thinking or speaking, then resume listening", () => {
    const thinking = run([{ type: "START" }, user]);
    const speaking = run([reply], thinking);

    expect(run([{ type: "INTERRUPT" }], thinking).status).toBe("interrupted");
    expect(run([{ type: "INTERRUPT" }], speaking).status).toBe("interrupted");
    expect(run([{ type: "INTERRUPT" }, { type: "RESUME" }], speaking).status).toBe("listening");
  });

  test("the user can speak again straight after an interruption", () => {
    const interrupted = run([{ type: "START" }, user, reply, { type: "INTERRUPT" }]);

    expect(run([user], interrupted).status).toBe("thinking");
  });

  test("a late reply after an interruption is ignored", () => {
    const interrupted = run([{ type: "START" }, user, { type: "INTERRUPT" }]);

    expect(run([reply, { type: "SPEAK_DONE" }], interrupted)).toBe(interrupted);
  });
});

describe("errors", () => {
  test("a failure shows the message and keeps the transcript", () => {
    const state = run([{ type: "START" }, user, { type: "FAIL", message: "boom" }]);

    expect(state.status).toBe("error");
    expect(state.errorMessage).toBe("boom");
    expect(state.transcript).toHaveLength(1);
  });

  test("dismissing an error returns to idle and clears the message", () => {
    const state = run([{ type: "START" }, { type: "FAIL", message: "boom" }, { type: "DISMISS_ERROR" }]);

    expect(state.status).toBe("idle");
    expect(state.errorMessage).toBeNull();
  });

  test("a failure while idle is ignored", () => {
    expect(run([{ type: "FAIL", message: "boom" }])).toBe(initialVoiceState);
  });
});

describe("stopping and restarting", () => {
  test("ending a session returns to idle and keeps the transcript visible", () => {
    const state = run([{ type: "START" }, user, reply, { type: "STOP" }]);

    expect(state.status).toBe("idle");
    expect(state.transcript).toHaveLength(2);
  });

  test("starting a new session clears the old transcript", () => {
    const state = run([{ type: "START" }, user, { type: "STOP" }, { type: "START" }]);

    expect(state.status).toBe("listening");
    expect(state.transcript).toEqual([]);
  });
});

describe("transitions that are not allowed", () => {
  const events: Record<string, VoiceEvent> = {
    START: { type: "START" },
    USER_TEXT: user,
    ASSISTANT_TEXT: reply,
    SPEAK_DONE: { type: "SPEAK_DONE" },
    INTERRUPT: { type: "INTERRUPT" },
    RESUME: { type: "RESUME" },
    DISMISS_ERROR: { type: "DISMISS_ERROR" },
  };

  // Every state keyed by the events that must leave it unchanged.
  const ignored: Record<VoiceState, string[]> = {
    idle: ["ASSISTANT_TEXT", "SPEAK_DONE", "INTERRUPT", "RESUME", "DISMISS_ERROR", "USER_TEXT"],
    listening: ["START", "ASSISTANT_TEXT", "SPEAK_DONE", "INTERRUPT", "RESUME", "DISMISS_ERROR"],
    thinking: ["START", "USER_TEXT", "SPEAK_DONE", "RESUME", "DISMISS_ERROR"],
    speaking: ["START", "USER_TEXT", "ASSISTANT_TEXT", "RESUME", "DISMISS_ERROR"],
    interrupted: ["START", "ASSISTANT_TEXT", "SPEAK_DONE", "INTERRUPT", "DISMISS_ERROR"],
    error: ["START", "USER_TEXT", "ASSISTANT_TEXT", "SPEAK_DONE", "INTERRUPT", "RESUME"],
  };

  const reach: Record<VoiceState, VoiceEvent[]> = {
    idle: [],
    listening: [{ type: "START" }],
    thinking: [{ type: "START" }, user],
    speaking: [{ type: "START" }, user, reply],
    interrupted: [{ type: "START" }, user, { type: "INTERRUPT" }],
    error: [{ type: "START" }, { type: "FAIL", message: "boom" }],
  };

  for (const [status, names] of Object.entries(ignored) as [VoiceState, string[]][]) {
    for (const name of names) {
      test(`${name} is ignored while ${status}`, () => {
        const state = run(reach[status]);
        const event = events[name];
        expect(event).toBeDefined();

        expect(voiceReducer(state, event as VoiceEvent)).toBe(state);
      });
    }
  }
});
