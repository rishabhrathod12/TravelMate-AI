/**
 * What the voice panel needs from a voice back end (ADR 0002). The panel and the state machine
 * depend on this interface only, never on a vendor. Only a mock implementation exists.
 */
export interface VoiceAdapter {
  /** Shown to the user, for example "Mock voice". */
  readonly name: string;
  /** True for any adapter that does not talk to a real service. The panel then says so. */
  readonly isMock: boolean;
  /** False when nothing is played aloud, so the panel never claims otherwise. */
  readonly playsAudio: boolean;
  /** The assistant's next reply to what the user said. Rejects on failure or when aborted. */
  respond(userText: string, signal: AbortSignal): Promise<string>;
  /** Says the reply aloud. Resolves when finished; rejects when aborted. */
  speak(text: string, signal: AbortSignal): Promise<void>;
}

export class VoiceAbortedError extends Error {
  constructor() {
    super("The voice step was interrupted");
    this.name = "VoiceAbortedError";
  }
}
