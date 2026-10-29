import { VoiceApiError, voiceSessionApi, type VoiceSessionApi } from "../api/voiceSessions";
import {
  VoiceConnectionError,
  type AdapterEvent,
  type AdapterListener,
  type VoiceAdapter,
} from "./VoiceAdapter";

export const NO_ASSISTANT_NOTICE =
  "No assistant is connected yet, so I can't answer. Your message was not sent to any assistant or voice service.";

export interface SessionAdapterOptions {
  api?: VoiceSessionApi;
  /** How often the server is asked whether the session is still alive. */
  pollMs?: number;
}

function connectionErrorFor(error: unknown): VoiceConnectionError {
  if (error instanceof VoiceApiError) {
    if (error.status === null) {
      return new VoiceConnectionError("unavailable", "The TravelMate server could not be reached.");
    }
    if (error.status === 404) {
      // A normal server start has no voice routes at all.
      return new VoiceConnectionError("unavailable", "Voice sessions are turned off on this server.");
    }
    if (error.status === 429) {
      return new VoiceConnectionError(
        "limit_reached",
        error.detail ?? "The voice session limit has been reached.",
      );
    }
  }
  return new VoiceConnectionError("unknown", "The voice session could not be opened.");
}

function eventFor(error: unknown): AdapterEvent {
  if (error instanceof VoiceApiError && (error.status === 404 || error.status === 410)) {
    return {
      type: "error",
      code: "session_expired",
      message: "The voice session has ended. Start a new one.",
    };
  }
  return {
    type: "error",
    code: "connection",
    message: "Lost contact with the TravelMate server.",
  };
}

/**
 * Opens a real session on the backend and nothing more. The session carries no audio, there is no
 * voice service and no assistant, so this adapter never claims to hear or speak: `hearsUser` and
 * `playsAudio` are false, it never asks the browser for the microphone, and a typed message gets a
 * plain notice saying nobody can answer yet. It exists to exercise the real session limits,
 * expiry and ownership checks from the interface.
 */
export function createSessionOnlyAdapter(options: SessionAdapterOptions = {}): VoiceAdapter {
  const api = options.api ?? voiceSessionApi;
  const pollMs = options.pollMs ?? 10_000;

  let listener: AdapterListener | null = null;
  let sessionId: string | null = null;
  let opening: AbortController | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;

  const emit = (event: AdapterEvent) => listener?.(event);

  function stopPolling() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function startPolling(id: string) {
    stopPolling();
    timer = setInterval(() => {
      api.read(id).catch((error: unknown) => {
        // A failed check ends the watch: one clear error, not one per tick.
        if (sessionId === id) {
          stopPolling();
          emit(eventFor(error));
        }
      });
    }, pollMs);
  }

  return {
    name: "Voice session (no audio)",
    isMock: false,
    playsAudio: false,
    hearsUser: false,
    audioDisclosure:
      "This opens a session on the TravelMate server. No audio is captured, recorded or sent anywhere, and no voice service is connected.",

    async connect(_options, nextListener) {
      // `microphone` is ignored on purpose: there is nothing that could hear or use it.
      listener = nextListener;
      const controller = new AbortController();
      opening = controller;
      let info;
      try {
        info = await api.create(controller.signal);
      } catch (error) {
        if (controller.signal.aborted) {
          throw new VoiceConnectionError("connection", "The session was closed.");
        }
        throw connectionErrorFor(error);
      } finally {
        if (opening === controller) {
          opening = null;
        }
      }
      if (controller.signal.aborted) {
        // Closed while opening: do not leave a session behind on the server.
        void api.end(info.session_id).catch(() => undefined);
        throw new VoiceConnectionError("connection", "The session was closed.");
      }
      sessionId = info.session_id;
      startPolling(info.session_id);
    },

    disconnect() {
      stopPolling();
      opening?.abort();
      opening = null;
      const id = sessionId;
      sessionId = null;
      listener = null;
      if (id !== null) {
        void api.end(id).catch(() => undefined);
      }
    },

    setMuted() {
      // Nothing is being heard, so there is nothing to mute.
    },

    interrupt() {
      // Nothing is being said, so there is nothing to interrupt.
    },

    sendText() {
      const id = sessionId;
      if (id === null) {
        return;
      }
      emit({ type: "thinking" });
      api.activity(id).then(
        () => {
          if (sessionId !== id) {
            return;
          }
          emit({ type: "transcript", speaker: "assistant", text: NO_ASSISTANT_NOTICE, source: "notice" });
          emit({ type: "listening" });
        },
        (error: unknown) => {
          if (sessionId === id) {
            stopPolling();
            emit(eventFor(error));
          }
        },
      );
    },
  };
}
