/**
 * The voice session as a pure state machine (docs/VOICE_ASSISTANT_PLAN.md, V2).
 *
 * It knows nothing about microphones, audio or providers. An event that is not allowed in the
 * current state is ignored, so a late or duplicate event from an adapter cannot corrupt the session.
 */

export type VoiceState = "idle" | "listening" | "thinking" | "speaking" | "interrupted" | "error";

export type TranscriptSource = "typed" | "simulated" | "mock-reply";

export interface TranscriptEntry {
  id: number;
  speaker: "user" | "assistant";
  text: string;
  source: TranscriptSource;
}

export interface VoiceSessionState {
  status: VoiceState;
  transcript: readonly TranscriptEntry[];
  errorMessage: string | null;
  nextId: number;
}

export type VoiceEvent =
  | { type: "START" }
  | { type: "USER_TEXT"; text: string; source: "typed" | "simulated" }
  | { type: "ASSISTANT_TEXT"; text: string }
  | { type: "SPEAK_DONE" }
  | { type: "INTERRUPT" }
  | { type: "RESUME" }
  | { type: "FAIL"; message: string }
  | { type: "DISMISS_ERROR" }
  | { type: "STOP" };

export const initialVoiceState: VoiceSessionState = {
  status: "idle",
  transcript: [],
  errorMessage: null,
  nextId: 1,
};

function append(
  state: VoiceSessionState,
  speaker: TranscriptEntry["speaker"],
  text: string,
  source: TranscriptSource,
): Pick<VoiceSessionState, "transcript" | "nextId"> {
  return {
    transcript: [...state.transcript, { id: state.nextId, speaker, text, source }],
    nextId: state.nextId + 1,
  };
}

export function voiceReducer(state: VoiceSessionState, event: VoiceEvent): VoiceSessionState {
  switch (event.type) {
    case "START":
      // A new session starts clean. Leaving an error keeps what was said so far.
      if (state.status === "idle") {
        return { ...initialVoiceState, status: "listening" };
      }
      return state;

    case "USER_TEXT": {
      const text = event.text.trim();
      if (text === "" || (state.status !== "listening" && state.status !== "interrupted")) {
        return state;
      }
      return { ...state, ...append(state, "user", text, event.source), status: "thinking" };
    }

    case "ASSISTANT_TEXT":
      if (state.status !== "thinking") {
        return state;
      }
      return {
        ...state,
        ...append(state, "assistant", event.text, "mock-reply"),
        status: "speaking",
      };

    case "SPEAK_DONE":
      return state.status === "speaking" ? { ...state, status: "listening" } : state;

    case "INTERRUPT":
      return state.status === "thinking" || state.status === "speaking"
        ? { ...state, status: "interrupted" }
        : state;

    case "RESUME":
      return state.status === "interrupted" ? { ...state, status: "listening" } : state;

    case "FAIL":
      if (state.status === "idle" || state.status === "error") {
        return state;
      }
      return { ...state, status: "error", errorMessage: event.message };

    case "DISMISS_ERROR":
      return state.status === "error" ? { ...state, status: "idle", errorMessage: null } : state;

    case "STOP":
      return state.status === "idle" ? state : { ...state, status: "idle", errorMessage: null };
  }
}
