import { useId } from "react";

import type { VoiceAdapter } from "../../voice/VoiceAdapter";
import { useVoiceSession } from "../../voice/useVoiceSession";
import type { VoiceSessionState } from "../../voice/voiceMachine";
import { StatusMessage } from "../StatusMessage";
import { DevMockControls } from "./DevMockControls";
import { MicPermissionNotice } from "./MicPermissionNotice";
import { TextChat } from "./TextChat";
import { VoiceOrb } from "./VoiceOrb";
import { VoiceTranscript } from "./VoiceTranscript";

interface VoiceModeProps {
  /** `null` when no voice back end is available in this build. */
  adapter: VoiceAdapter | null;
  /** Lets the user go straight back to the trip form. */
  onReturnToPlanner?: () => void;
}

function statusText(state: VoiceSessionState, playsAudio: boolean): string {
  switch (state.status) {
    case "idle":
      return "Ready when you are.";
    case "connecting":
      return "Connecting…";
    case "listening":
      if (state.mode === "text") {
        return "Ready. Type your message.";
      }
      return state.muted ? "Muted. TravelMate can't hear you." : "Listening… go ahead and speak.";
    case "thinking":
      return "Thinking…";
    case "speaking":
      return playsAudio ? "Speaking…" : "Speaking… (text only, no sound)";
    case "error":
      return "Something went wrong.";
  }
}

/**
 * The conversational voice interface: one main button, a clear state, and the controls needed to
 * mute, interrupt and end. It only ever shows what the adapter reports.
 */
export function VoiceMode({ adapter, onReturnToPlanner }: VoiceModeProps) {
  const session = useVoiceSession(adapter);
  const { state } = session;
  const headingId = useId();
  const noteId = useId();

  const active = state.status !== "idle" && state.status !== "error";
  const inSession = state.status === "listening" || state.status === "thinking" || state.status === "speaking";

  return (
    <section className="card voice-mode" aria-labelledby={headingId}>
      <h2 id={headingId}>Talk to TravelMate</h2>

      {adapter?.isMock === true && (
        <p className="voice-mock-note" role="note">
          <strong>MOCK voice (development build).</strong> No microphone is used and no sound is
          played or recorded. Replies are scripted and nothing you say or type is understood or sent
          anywhere. Real voice is not built yet.
        </p>
      )}

      {adapter === null && (
        <StatusMessage kind="info" title="Voice isn't available yet">
          Voice conversations need a connected voice service, which this version does not have. Use
          the trip form to plan a trip.
        </StatusMessage>
      )}

      <div className="voice-stage">
        <VoiceOrb status={state.status} muted={state.muted} />
        <p className="voice-status" role="status">
          {statusText(state, adapter?.playsAudio ?? false)}
        </p>
      </div>

      {state.status === "error" && state.error !== null && (
        <MicPermissionNotice
          code={state.error.code}
          message={state.error.message}
          onRetry={() => void session.retry()}
          onUseText={() => void session.startText()}
          onDismiss={session.dismissError}
        />
      )}

      <div className="voice-controls">
        {!active && state.status !== "error" && (
          <>
            <button
              type="button"
              className="button button-primary voice-main-button"
              onClick={() => void session.startVoice()}
              disabled={!session.available}
              aria-describedby={adapter?.audioDisclosure != null ? noteId : undefined}
            >
              Talk to TravelMate
            </button>
            {adapter?.audioDisclosure != null && (
              <p id={noteId} className="field-hint">
                {adapter.audioDisclosure}
              </p>
            )}
          </>
        )}

        {state.status === "connecting" && (
          <button type="button" className="button button-secondary" disabled>
            Connecting…
          </button>
        )}

        {inSession && (
          <div className="button-row">
            {state.mode === "voice" && (
              <button
                type="button"
                className="button button-secondary"
                aria-pressed={state.muted}
                onClick={session.toggleMute}
              >
                {state.muted ? "Unmute" : "Mute"}
              </button>
            )}
            {state.status === "speaking" && (
              <button type="button" className="button button-secondary" onClick={session.interrupt}>
                Interrupt
              </button>
            )}
            <button type="button" className="button button-secondary" onClick={session.stop}>
              End session
            </button>
          </div>
        )}

        {state.status === "connecting" && (
          <button type="button" className="button button-quiet" onClick={session.stop}>
            Cancel
          </button>
        )}
      </div>

      <TextChat
        disabled={!session.available || state.status === "connecting" || state.status === "error"}
        onSend={(text) => void session.sendText(text)}
      />

      <VoiceTranscript entries={state.transcript} />

      {adapter?.devControls !== undefined && <DevMockControls controls={adapter.devControls} />}

      {onReturnToPlanner !== undefined && (
        <p>
          <button type="button" className="button button-quiet" onClick={onReturnToPlanner}>
            Back to the trip form
          </button>
        </p>
      )}
    </section>
  );
}
