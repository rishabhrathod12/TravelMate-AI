import {
  VoiceConnectionError,
  type AdapterEvent,
  type AdapterListener,
  type VoiceAdapter,
} from "./VoiceAdapter";

/**
 * DEVELOPMENT MOCK. It uses no microphone, plays no sound and makes no network call. Its replies
 * are scripted and do not depend on what the user says. It is offered only in development builds
 * (see `chooseVoiceAdapter`) and is always labelled MOCK in the interface.
 */
export const MOCK_REPLIES: readonly string[] = [
  "Bilkul! Aap kis date ko travel karna chahte hain?",
  "Theek hai. Kitne log travel karenge?",
  "Mock mode mein main bas yeh scripted baatcheet dikha sakta hoon. Asli search aur kharcha baad ke milestones mein judenge.",
];

export const SIMULATED_USER_PHRASE = "Mujhe Indore se Goa jana hai. Saste options batao.";

export interface MockVoiceOptions {
  connectMs?: number;
  thinkMs?: number;
  speakMs?: number;
  /** Fail the reply at this zero-based turn, to exercise the error state. */
  failAtTurn?: number;
}

export function createMockVoiceAdapter(options: MockVoiceOptions = {}): VoiceAdapter {
  const connectMs = options.connectMs ?? 500;
  const thinkMs = options.thinkMs ?? 700;
  const speakMs = options.speakMs ?? 1500;

  let listener: AdapterListener | null = null;
  const timers = new Set<ReturnType<typeof setTimeout>>();
  let rejectConnect: ((error: Error) => void) | null = null;
  let connected = false;
  let microphone = false;
  let muted = false;
  let denyNextMicrophone = false;
  let turn = 0;

  const emit = (event: AdapterEvent) => listener?.(event);

  function later(ms: number, action: () => void) {
    const timer = setTimeout(() => {
      timers.delete(timer);
      action();
    }, ms);
    timers.add(timer);
  }

  function clearTimers() {
    timers.forEach(clearTimeout);
    timers.clear();
  }

  function reply() {
    clearTimers();
    emit({ type: "thinking" });
    later(thinkMs, () => {
      const current = turn;
      turn += 1;
      if (options.failAtTurn === current) {
        emit({ type: "error", code: "connection", message: "Mock voice failure (simulated)." });
        return;
      }
      const text = MOCK_REPLIES[Math.min(current, MOCK_REPLIES.length - 1)] ?? "";
      emit({ type: "transcript", speaker: "assistant", text, source: "mock-reply" });
      emit({ type: "speaking" });
      later(speakMs, () => emit({ type: "listening" }));
    });
  }

  return {
    name: "Mock voice",
    isMock: true,
    playsAudio: false,
    // The mock pretends to listen so the screens can be reviewed; its note says it does not.
    hearsUser: true,
    audioDisclosure: null,

    devControls: {
      simulateUserPhrase() {
        if (!connected || !microphone || muted) {
          return;
        }
        emit({
          type: "transcript",
          speaker: "user",
          text: SIMULATED_USER_PHRASE,
          source: "simulated",
        });
        reply();
      },
      simulateError() {
        if (connected) {
          clearTimers();
          emit({ type: "error", code: "connection", message: "Simulated connection loss." });
        }
      },
      denyMicrophoneNextTime() {
        denyNextMicrophone = true;
      },
    },

    connect(connectOptions, nextListener) {
      listener = nextListener;
      microphone = connectOptions.microphone;
      return new Promise<void>((resolve, reject) => {
        rejectConnect = reject;
        later(connectMs, () => {
          rejectConnect = null;
          if (microphone && denyNextMicrophone) {
            denyNextMicrophone = false;
            reject(
              new VoiceConnectionError("permission_denied", "Microphone permission was refused."),
            );
            return;
          }
          connected = true;
          resolve();
        });
      });
    },

    disconnect() {
      clearTimers();
      rejectConnect?.(new VoiceConnectionError("connection", "The session was closed."));
      rejectConnect = null;
      connected = false;
      muted = false;
      listener = null;
    },

    setMuted(next) {
      muted = next;
    },

    interrupt() {
      if (connected) {
        clearTimers();
        emit({ type: "listening" });
      }
    },

    sendText() {
      if (connected) {
        reply();
      }
    },
  };
}
