import { useId } from "react";

import type { VoiceAdapter } from "../../voice/VoiceAdapter";
import { MicIcon } from "./icons";

interface VoiceButtonProps {
  /** `null` when this build has no voice back end (production): the button is then disabled. */
  adapter: VoiceAdapter | null;
  connecting: boolean;
  onStart: () => void;
}

/** What the adapter is, in words: a mock or a session-only adapter is never presented as voice. */
function adapterNote(adapter: VoiceAdapter | null): string | null {
  // `import.meta.env.DEV` is a build-time constant: a production build has no adapter and drops
  // these development-only labels.
  if (!import.meta.env.DEV || adapter === null) {
    return null;
  }
  if (adapter.isMock) {
    return "MOCK voice (development build): no microphone, no sound, scripted replies.";
  }
  if (!adapter.hearsUser) {
    return "Voice session only (development build): TravelMate can't hear or speak yet.";
  }
  return null;
}

/** The one prominent voice button of the home screen. It starts the existing voice session. */
export function VoiceButton({ adapter, connecting, onStart }: VoiceButtonProps) {
  const labelId = useId();
  const hintId = useId();
  const available = adapter !== null;
  const note = adapterNote(adapter);

  return (
    <div className="voice-button-block">
      <button
        type="button"
        className="voice-circle"
        onClick={onStart}
        disabled={!available || connecting}
        aria-labelledby={labelId}
        aria-describedby={hintId}
      >
        <MicIcon />
      </button>
      <p id={labelId} className="voice-button-label">
        Talk to TravelMate
      </p>
      <p id={hintId} className="voice-button-hint">
        {available
          ? connecting
            ? "Connecting…"
            : "Tap to start a voice conversation"
          : "Voice isn't available yet in this version."}
      </p>
      {note !== null && (
        <p className="voice-button-note" role="note">
          {note}
        </p>
      )}
    </div>
  );
}
