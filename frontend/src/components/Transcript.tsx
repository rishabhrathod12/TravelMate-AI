import type { TranscriptEntry, TranscriptSource } from "../voice/voiceMachine";

const SOURCE_LABEL: Record<TranscriptSource, string> = {
  typed: "typed",
  simulated: "simulated, not heard",
  "mock-reply": "MOCK reply",
};

export function Transcript({ entries }: { entries: readonly TranscriptEntry[] }) {
  if (entries.length === 0) {
    return <p className="field-hint">The conversation will appear here.</p>;
  }
  return (
    <ol className="transcript" aria-label="Transcript">
      {entries.map((entry) => (
        <li key={entry.id} className={`transcript-entry transcript-${entry.speaker}`}>
          <span className="transcript-speaker">
            {entry.speaker === "user" ? "You" : "Assistant"}
            <span className="transcript-source"> ({SOURCE_LABEL[entry.source]})</span>
          </span>
          <span className="transcript-text">{entry.text}</span>
        </li>
      ))}
    </ol>
  );
}
