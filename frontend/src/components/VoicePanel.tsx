import { useId, useState, type FormEvent } from "react";

import type { VoiceAdapter } from "../voice/VoiceAdapter";
import { useVoiceSession } from "../voice/useVoiceSession";
import type { VoiceState } from "../voice/voiceMachine";
import { StatusMessage } from "./StatusMessage";
import { Transcript } from "./Transcript";

const STATE_LABEL: Record<VoiceState, string> = {
  idle: "Idle",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  interrupted: "Interrupted",
  error: "Error",
};

/**
 * The voice section of the planning page. With the mock adapter it uses no microphone, plays no
 * sound and understands nothing; it exists to review the layout, states and text fallback.
 */
export function VoicePanel({ adapter }: { adapter: VoiceAdapter }) {
  const session = useVoiceSession(adapter);
  const { state } = session;
  const [draft, setDraft] = useState("");
  const headingId = useId();
  const inputId = useId();

  const active = state.status !== "idle" && state.status !== "error";

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (draft.trim() === "") {
      return;
    }
    session.sendText(draft);
    setDraft("");
  }

  return (
    <section className="card voice-panel" aria-labelledby={headingId}>
      <h2 id={headingId}>Voice assistant{adapter.isMock ? " (mock)" : ""}</h2>

      {adapter.isMock && (
        <p className="voice-mock-note" role="note">
          <strong>MOCK voice.</strong> No microphone is used and no audio is played or recorded.
          Replies are scripted: nothing you say or type is understood, saved or sent anywhere.
          Real voice is not built yet.
        </p>
      )}

      <p className={`voice-state voice-state-${state.status}`} role="status">
        <span className="voice-state-label">Status:</span> {STATE_LABEL[state.status]}
        {!adapter.playsAudio && state.status === "speaking" ? " (text only, no sound)" : ""}
      </p>

      <div className="button-row">
        {active ? (
          <button type="button" className="button button-secondary" onClick={session.stop}>
            End session
          </button>
        ) : (
          <button type="button" className="button button-primary" onClick={session.start}>
            Start session
          </button>
        )}
        <button
          type="button"
          className="button button-secondary"
          onClick={session.simulateSpeech}
          disabled={state.status !== "listening" && state.status !== "interrupted"}
        >
          Simulate a spoken phrase
        </button>
        <button
          type="button"
          className="button button-secondary"
          onClick={session.interrupt}
          disabled={state.status !== "thinking" && state.status !== "speaking"}
        >
          Interrupt
        </button>
        <button
          type="button"
          className="button button-secondary"
          onClick={session.resume}
          disabled={state.status !== "interrupted"}
        >
          Resume listening
        </button>
        <button
          type="button"
          className="button button-quiet"
          onClick={session.simulateError}
          disabled={!active}
        >
          Simulate an error
        </button>
      </div>

      {state.status === "error" && (
        <StatusMessage kind="error" title="Voice problem">
          <p>{state.errorMessage}</p>
          <button type="button" className="button button-small" onClick={session.dismissError}>
            Dismiss
          </button>
        </StatusMessage>
      )}

      <form className="voice-text-fallback" onSubmit={handleSubmit}>
        <label htmlFor={inputId}>Type a message instead</label>
        <div className="voice-text-row">
          <input
            id={inputId}
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={!session.canSend}
            autoComplete="off"
          />
          <button
            type="submit"
            className="button button-primary"
            disabled={!session.canSend || draft.trim() === ""}
          >
            Send
          </button>
        </div>
      </form>

      <h3>Transcript</h3>
      <Transcript entries={state.transcript} />
    </section>
  );
}
