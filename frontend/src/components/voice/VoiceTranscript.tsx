import type { TranscriptSource } from "../../voice/VoiceAdapter";
import type { TranscriptEntry } from "../../voice/voiceMachine";
import { useFollowBottomIn } from "./useFollowBottomIn";

const SOURCE_LABEL: Record<TranscriptSource, string> = {
  voice: "spoken",
  typed: "typed",
  simulated: "simulated, not heard",
  assistant: "assistant",
  "mock-reply": "Scripted reply",
  notice: "notice, not an answer",
};

/**
 * A compact, scrollable conversation. It sits below the controls and stays small, so it scrolls
 * inside its own box: that box follows the newest entry while the reader is at the bottom, and
 * leaves a reader who scrolled up alone (`useFollowBottomIn`).
 */
export function VoiceTranscript({ entries }: { entries: readonly TranscriptEntry[] }) {
  const { ref, followIfPinned } = useFollowBottomIn<HTMLOListElement>({
    itemCount: entries.length,
    // Only a typed message is something the reader deliberately sent; what they say aloud is not.
    forceToEnd: entries[entries.length - 1]?.source === "typed",
  });
  if (entries.length === 0) {
    return null;
  }
  return (
    <details
      className="voice-transcript"
      open
      onToggle={(event) => {
        if (event.currentTarget.open) {
          followIfPinned();
        }
      }}
    >
      <summary>
        Conversation ({entries.length} {entries.length === 1 ? "message" : "messages"})
      </summary>
      {/* Focusable so keyboard users can scroll it. role="log" is announced politely. */}
      <ol className="transcript" role="log" aria-label="Transcript" tabIndex={0} ref={ref}>
        {entries.map((entry) => (
          <li key={entry.id} className={`transcript-entry transcript-${entry.speaker}`}>
            <span className="transcript-speaker">
              {entry.speaker === "user" ? "You" : "TravelMate"}
              <span className="transcript-source"> ({SOURCE_LABEL[entry.source]})</span>
            </span>
            <span className="transcript-text">{entry.text}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
