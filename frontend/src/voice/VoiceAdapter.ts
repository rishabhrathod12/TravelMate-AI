/**
 * What the voice interface needs from a voice back end (ADR 0002). The state machine and the
 * components depend on this interface only, never on a vendor. Only a development mock exists;
 * a real adapter is a later step (docs/VOICE_ASSISTANT_PLAN.md).
 */

export type VoiceErrorCode =
  | "permission_denied"
  | "no_microphone"
  | "connection"
  | "unavailable"
  | "limit_reached"
  | "session_expired"
  | "unknown";

/** `notice` is a message from the system itself, not an answer from an assistant. */
export type TranscriptSource =
  | "voice"
  | "typed"
  | "simulated"
  | "assistant"
  | "mock-reply"
  | "notice";

/** Events an adapter reports after a connection is made. */
export type AdapterEvent =
  | { type: "listening" }
  | { type: "thinking" }
  | { type: "speaking" }
  | { type: "transcript"; speaker: "user" | "assistant"; text: string; source: TranscriptSource }
  | { type: "error"; code: VoiceErrorCode; message: string };

export type AdapterListener = (event: AdapterEvent) => void;

/** Thrown by `connect` when the session cannot start. */
export class VoiceConnectionError extends Error {
  readonly code: VoiceErrorCode;

  constructor(code: VoiceErrorCode, message: string) {
    super(message);
    this.name = "VoiceConnectionError";
    this.code = code;
  }
}

/** Controls that exist only on a development mock. Real adapters never have them. */
export interface DevMockControls {
  simulateUserPhrase(): void;
  simulateError(): void;
  denyMicrophoneNextTime(): void;
}

export interface VoiceAdapter {
  /** Shown to the user, for example "Mock voice". */
  readonly name: string;
  /** True for any adapter that does not talk to a real service. The interface then says so. */
  readonly isMock: boolean;
  /** False when nothing is played aloud, so the interface never claims otherwise. */
  readonly playsAudio: boolean;
  /**
   * False when the session cannot hear the user at all. The interface then says so and offers
   * no mute control, instead of showing "Listening". A labelled mock may say true to let the
   * screens be reviewed.
   */
  readonly hearsUser: boolean;
  /**
   * Shown before the first use: who processes the audio. `null` only when no audio leaves the
   * device, as in the mock.
   */
  readonly audioDisclosure: string | null;
  /** Present on development mocks only. */
  readonly devControls?: DevMockControls;

  /**
   * Opens a session. With `microphone: true` this asks the browser for microphone permission and
   * rejects with a `VoiceConnectionError` if it is refused. With `microphone: false` it opens a
   * text-only session. Resolves when the session is ready.
   */
  connect(options: { microphone: boolean }, listener: AdapterListener): Promise<void>;
  /** Closes the session and releases the microphone. Safe to call at any time. */
  disconnect(): void;
  /** Stops sending the user's voice. Has no effect on a text-only session. */
  setMuted(muted: boolean): void;
  /** Stops the assistant speaking and returns to listening. */
  interrupt(): void;
  /** A typed message from the user. */
  sendText(text: string): void;
}
