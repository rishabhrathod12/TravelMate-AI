import { useCallback, useEffect, useReducer, useRef } from "react";

import { SIMULATED_USER_PHRASE } from "./mockAdapter";
import { VoiceAbortedError, type VoiceAdapter } from "./VoiceAdapter";
import { initialVoiceState, voiceReducer } from "./voiceMachine";

/** Runs a voice session: the state machine plus the adapter calls that drive it. */
export function useVoiceSession(adapter: VoiceAdapter) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoiceState);
  const current = useRef<AbortController | null>(null);

  const abortCurrent = useCallback(() => {
    current.current?.abort();
    current.current = null;
  }, []);

  // Leaving the page must not leave a reply running.
  useEffect(() => abortCurrent, [abortCurrent]);

  const runTurn = useCallback(
    async (userText: string) => {
      abortCurrent();
      const controller = new AbortController();
      current.current = controller;
      try {
        const reply = await adapter.respond(userText, controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        dispatch({ type: "ASSISTANT_TEXT", text: reply });
        await adapter.speak(reply, controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        dispatch({ type: "SPEAK_DONE" });
      } catch (error) {
        if (controller.signal.aborted || error instanceof VoiceAbortedError) {
          return;
        }
        dispatch({
          type: "FAIL",
          message: "The voice assistant could not answer. You can try again or type instead.",
        });
      }
    },
    [adapter, abortCurrent],
  );

  const canSend =
    state.status === "idle" || state.status === "listening" || state.status === "interrupted";

  const send = useCallback(
    (text: string, source: "typed" | "simulated") => {
      if (!canSend || text.trim() === "") {
        return;
      }
      if (state.status === "idle") {
        dispatch({ type: "START" });
      }
      dispatch({ type: "USER_TEXT", text, source });
      void runTurn(text.trim());
    },
    [canSend, state.status, runTurn],
  );

  return {
    state,
    canSend,
    start: useCallback(() => dispatch({ type: "START" }), []),
    stop: useCallback(() => {
      abortCurrent();
      dispatch({ type: "STOP" });
    }, [abortCurrent]),
    sendText: useCallback((text: string) => send(text, "typed"), [send]),
    simulateSpeech: useCallback(() => send(SIMULATED_USER_PHRASE, "simulated"), [send]),
    interrupt: useCallback(() => {
      abortCurrent();
      dispatch({ type: "INTERRUPT" });
    }, [abortCurrent]),
    resume: useCallback(() => dispatch({ type: "RESUME" }), []),
    simulateError: useCallback(() => {
      abortCurrent();
      dispatch({ type: "FAIL", message: "Simulated error. Nothing is wrong with your device." });
    }, [abortCurrent]),
    dismissError: useCallback(() => dispatch({ type: "DISMISS_ERROR" }), []),
  };
}
