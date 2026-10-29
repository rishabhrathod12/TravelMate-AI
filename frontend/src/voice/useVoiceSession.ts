import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  VoiceConnectionError,
  type AdapterEvent,
  type VoiceAdapter,
} from "./VoiceAdapter";
import { initialVoiceState, voiceReducer, type VoiceMode } from "./voiceMachine";

/** Runs a voice session: the state machine plus the adapter calls that drive it. */
export function useVoiceSession(adapter: VoiceAdapter | null) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoiceState);
  // Bumped whenever a session is ended, so a connection that finishes late is ignored.
  const generation = useRef(0);

  const onEvent = useCallback((event: AdapterEvent) => {
    switch (event.type) {
      case "listening":
      case "thinking":
      case "speaking":
        dispatch({ type: "PHASE", phase: event.type });
        break;
      case "transcript":
        dispatch({
          type: "TRANSCRIPT",
          speaker: event.speaker,
          text: event.text,
          source: event.source,
        });
        break;
      case "error":
        dispatch({ type: "FAIL", code: event.code, message: event.message });
        break;
    }
  }, []);

  // Leaving the page must release the microphone and stop any reply.
  useEffect(
    () => () => {
      generation.current += 1;
      adapter?.disconnect();
    },
    [adapter],
  );

  const connect = useCallback(
    async (mode: VoiceMode): Promise<boolean> => {
      if (adapter === null) {
        return false;
      }
      generation.current += 1;
      const mine = generation.current;
      dispatch({ type: "CONNECT", mode });
      try {
        await adapter.connect({ microphone: mode === "voice" }, onEvent);
      } catch (error) {
        if (generation.current === mine) {
          dispatch(
            error instanceof VoiceConnectionError
              ? { type: "FAIL", code: error.code, message: error.message }
              : { type: "FAIL", code: "unknown", message: "The voice session could not start." },
          );
        }
        return false;
      }
      if (generation.current !== mine) {
        return false;
      }
      dispatch({ type: "CONNECTED" });
      return true;
    },
    [adapter, onEvent],
  );

  const stop = useCallback(() => {
    generation.current += 1;
    adapter?.disconnect();
    dispatch({ type: "END" });
  }, [adapter]);

  const toggleMute = useCallback(() => {
    adapter?.setMuted(!state.muted);
    dispatch({ type: "SET_MUTED", muted: !state.muted });
  }, [adapter, state.muted]);

  const interrupt = useCallback(() => adapter?.interrupt(), [adapter]);

  const sendText = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (adapter === null || text === "" || state.status === "connecting" || state.status === "error") {
        return;
      }
      if (state.status === "idle" && !(await connect("text"))) {
        return;
      }
      dispatch({ type: "TRANSCRIPT", speaker: "user", text, source: "typed" });
      adapter.sendText(text);
    },
    [adapter, connect, state.status],
  );

  return {
    state,
    available: adapter !== null,
    startVoice: useCallback(() => connect("voice"), [connect]),
    startText: useCallback(() => connect("text"), [connect]),
    retry: useCallback(() => connect(state.mode), [connect, state.mode]),
    stop,
    toggleMute,
    interrupt,
    sendText,
    dismissError: useCallback(() => dispatch({ type: "DISMISS_ERROR" }), []),
  };
}
