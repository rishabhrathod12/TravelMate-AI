import type { VoiceState } from "../../voice/voiceMachine";

/** The animated indicator. Decorative: the status text next to it is what assistive tech reads. */
export function VoiceOrb({ status, muted }: { status: VoiceState; muted: boolean }) {
  return (
    <div
      className={`voice-orb voice-orb-${status}${muted ? " voice-orb-muted" : ""}`}
      aria-hidden="true"
    >
      <span className="voice-orb-ring" />
      <span className="voice-orb-core" />
    </div>
  );
}
