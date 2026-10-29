import type { TranscriptSource } from "../../voice/VoiceAdapter";
import type { TranscriptEntry } from "../../voice/voiceMachine";

const SOURCE_LABEL: Record<TranscriptSource, string> = {
  voice: "spoken",
  typed: "typed",
  simulated: "simulated, not heard",
  assistant: "assistant",
  "mock-reply": "MOCK reply",
  notice: "notice, not an answer",
};

/** A compact, scrollable conversation. It sits below the controls and stays small. */
export function VoiceTranscript({ entries }: { entries: readonly TranscriptEntry[] }) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <details className="voice-transcript" open>
      <summary>
        Conversation ({entries.length} {entries.length === 1 ? "message" : "messages"})
      </summary>
      {/* Focusable so keyboard users can scroll it. role="log" is announced politely. */}
      <ol className="transcript" role="log" aria-label="Transcript" tabIndex={0}>
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
