/**
 * The voice session as a pure state machine (docs/VOICE_ASSISTANT_PLAN.md).
 *
 * It knows nothing about microphones, audio or providers. An event that is not allowed in the
 * current state is ignored, so a late or duplicate event from an adapter cannot corrupt the session.
 */

import type { TranscriptSource, VoiceErrorCode } from "./VoiceAdapter";

export type VoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";
export type VoiceMode = "voice" | "text";
export type VoicePhase = "listening" | "thinking" | "speaking";

export interface TranscriptEntry {
  id: number;
  speaker: "user" | "assistant";
  text: string;
  source: TranscriptSource;
}

export interface VoiceSessionState {
  status: VoiceState;
  mode: VoiceMode;
  muted: boolean;
  transcript: readonly TranscriptEntry[];
  error: { code: VoiceErrorCode; message: string } | null;
  nextId: number;
}

export type VoiceEvent =
  | { type: "CONNECT"; mode: VoiceMode }
  | { type: "CONNECTED" }
  | { type: "PHASE"; phase: VoicePhase }
  | { type: "TRANSCRIPT"; speaker: "user" | "assistant"; text: string; source: TranscriptSource }
  | { type: "SET_MUTED"; muted: boolean }
  | { type: "FAIL"; code: VoiceErrorCode; message: string }
  | { type: "DISMISS_ERROR" }
  | { type: "END" };

export const initialVoiceState: VoiceSessionState = {
  status: "idle",
  mode: "voice",
  muted: false,
  transcript: [],
  error: null,
  nextId: 1,
};

function isLive(status: VoiceState): status is VoicePhase {
  return status === "listening" || status === "thinking" || status === "speaking";
}

export function voiceReducer(state: VoiceSessionState, event: VoiceEvent): VoiceSessionState {
  switch (event.type) {
    case "CONNECT":
      if (state.status === "idle") {
        // A new session starts clean.
        return { ...initialVoiceState, status: "connecting", mode: event.mode };
      }
      if (state.status === "error") {
        // Trying again after an error keeps what was said so far.
        return { ...state, status: "connecting", mode: event.mode, muted: false, error: null };
      }
      return state;

    case "CONNECTED":
      return state.status === "connecting" ? { ...state, status: "listening" } : state;

    case "PHASE":
      return isLive(state.status) ? { ...state, status: event.phase } : state;

    case "TRANSCRIPT": {
      const text = event.text.trim();
      if (text === "" || !isLive(state.status)) {
        return state;
      }
      return {
        ...state,
        transcript: [
          ...state.transcript,
          { id: state.nextId, speaker: event.speaker, text, source: event.source },
        ],
        nextId: state.nextId + 1,
      };
    }

    case "SET_MUTED":
      // Muting only means something when a microphone is in use.
      return isLive(state.status) && state.mode === "voice"
        ? { ...state, muted: event.muted }
        : state;

    case "FAIL":
      if (state.status === "idle" || state.status === "error") {
        return state;
      }
      return {
        ...state,
        status: "error",
        muted: false,
        error: { code: event.code, message: event.message },
      };

    case "DISMISS_ERROR":
      return state.status === "error" ? { ...state, status: "idle", error: null } : state;

    case "END":
      return state.status === "idle" ? state : { ...state, status: "idle", muted: false, error: null };
  }
}
