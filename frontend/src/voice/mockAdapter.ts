import { VoiceAbortedError, type VoiceAdapter } from "./VoiceAdapter";

/** A scripted conversation. It does not read or understand what the user says. */
export const MOCK_REPLIES: readonly string[] = [
  "Bilkul! Aap kis date ko travel karna chahte hain?",
  "Theek hai. Kitne log travel karenge?",
  "Mock mode mein main bas yeh scripted baatcheet dikha sakta hoon. Asli search aur kharcha baad ke milestones mein judenge.",
];

export const SIMULATED_USER_PHRASE = "Mujhe Indore se Goa jana hai. Saste options batao.";

export interface MockVoiceOptions {
  thinkMs?: number;
  speakMs?: number;
  /** Fail the reply at this zero-based turn, to exercise the error state. */
  failAtTurn?: number;
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new VoiceAbortedError());
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new VoiceAbortedError());
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Mock voice: no microphone, no audio, no network. Replies come from MOCK_REPLIES in order and the
 * last one repeats. `speak` only waits, so the panel can show the speaking state.
 */
export function createMockVoiceAdapter(options: MockVoiceOptions = {}): VoiceAdapter {
  const thinkMs = options.thinkMs ?? 700;
  const speakMs = options.speakMs ?? 1200;
  let turn = 0;

  return {
    name: "Mock voice",
    isMock: true,
    playsAudio: false,
    async respond(_userText, signal) {
      await wait(thinkMs, signal);
      const current = turn;
      turn += 1;
      if (options.failAtTurn === current) {
        throw new Error("Mock voice failure (simulated)");
      }
      return MOCK_REPLIES[Math.min(current, MOCK_REPLIES.length - 1)] ?? "";
    },
    async speak(_text, signal) {
      await wait(speakMs, signal);
    },
  };
}
