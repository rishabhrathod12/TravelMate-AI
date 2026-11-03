import { realtimeVoiceApi, VoiceApiError, type RealtimeVoiceApi } from "../api/voiceSessions";
import {
  VoiceConnectionError,
  type AdapterEvent,
  type AdapterListener,
  type VoiceAdapter,
} from "./VoiceAdapter";

/**
 * Live spoken conversation through OpenAI Realtime (ADR 0008). Development builds only.
 *
 * The TravelMate server mints a short-lived secret; this adapter opens one WebRTC connection to
 * OpenAI with it, so microphone audio goes to OpenAI and the spoken reply comes back. The real API
 * key never reaches the browser. The secret is held in a local variable for the one request that
 * needs it and is never stored, logged or shown.
 *
 * The server fixed the model, voice, instructions and an empty tool list when it minted the
 * secret. This adapter sends no session settings and no tools. It only relays the person's voice
 * or typed text and shows what comes back, so it cannot search, book or approve anything.
 *
 * The OpenAI side was written from its public documentation and has not been exercised against
 * the live service by the project (ADR 0008): event names that are not recognised are ignored,
 * and any failure is reported with a short message that never repeats the provider's own text.
 */

export const OPENAI_CALLS_URL = "https://api.openai.com/v1/realtime/calls";
export const EVENTS_CHANNEL = "oai-events";

export const REALTIME_DISCLOSURE =
  "Your microphone audio is sent to OpenAI while this session is open, and OpenAI speaks the replies. The assistant can talk and cannot search, book or approve anything. TravelMate does not store the audio.";

/** The parts of the browser this adapter touches, so a test can supply fakes. */
export interface RtcEnvironment {
  getUserMedia(constraints: { audio: boolean }): Promise<RtcStream>;
  createPeer(): RtcPeer;
  createAudio(): RtcAudio;
  fetchText(url: string, init: { method: string; headers: Record<string, string>; body: string; signal?: AbortSignal }): Promise<{ ok: boolean; status: number; text(): Promise<string> }>;
  setTimer(callback: () => void, ms: number): unknown;
  clearTimer(handle: unknown): void;
}

export interface RtcTrack {
  enabled: boolean;
  stop(): void;
}
export interface RtcStream {
  getTracks(): RtcTrack[];
}
export interface RtcChannel {
  readyState: string;
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: (() => void) | null;
  send(data: string): void;
  close(): void;
}
export interface RtcPeer {
  ontrack: ((event: { streams: RtcStream[] }) => void) | null;
  onconnectionstatechange: (() => void) | null;
  connectionState: string;
  addTrack(track: RtcTrack, stream: RtcStream): void;
  createDataChannel(label: string): RtcChannel;
  createOffer(): Promise<{ type: string; sdp?: string }>;
  setLocalDescription(description: { type: string; sdp?: string }): Promise<void>;
  setRemoteDescription(description: { type: string; sdp: string }): Promise<void>;
  close(): void;
}
export interface RtcAudio {
  autoplay: boolean;
  srcObject: unknown;
  pause(): void;
}

export interface RealtimeAdapterOptions {
  api?: RealtimeVoiceApi;
  env?: RtcEnvironment;
}

function browserEnvironment(): RtcEnvironment {
  return {
    getUserMedia: (constraints) =>
      navigator.mediaDevices.getUserMedia(constraints) as unknown as Promise<RtcStream>,
    createPeer: () => new RTCPeerConnection() as unknown as RtcPeer,
    createAudio: () => new Audio() as unknown as RtcAudio,
    fetchText: (url, init) => fetch(url, init),
    setTimer: (callback, ms) => setTimeout(callback, ms),
    clearTimer: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  };
}

function connectionErrorFor(error: unknown): VoiceConnectionError {
  if (error instanceof VoiceApiError) {
    if (error.status === null) {
      return new VoiceConnectionError("unavailable", "The TravelMate server could not be reached.");
    }
    if (error.status === 404) {
      return new VoiceConnectionError("unavailable", "Live voice is turned off on this server.");
    }
    if (error.status === 429) {
      return new VoiceConnectionError(
        "limit_reached",
        error.detail ?? "The live voice limit has been reached.",
      );
    }
    if (error.status === 502) {
      return new VoiceConnectionError("unavailable", "The voice service could not start a session.");
    }
  }
  return new VoiceConnectionError("unknown", "The live voice session could not be opened.");
}

function microphoneError(error: unknown): VoiceConnectionError {
  const name = typeof error === "object" && error !== null ? (error as { name?: unknown }).name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return new VoiceConnectionError("permission_denied", "Microphone access was blocked.");
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return new VoiceConnectionError("no_microphone", "No microphone was found.");
  }
  return new VoiceConnectionError("no_microphone", "The microphone could not be used.");
}

function safeParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

/** Turns one message from OpenAI into at most one interface event. Unknown messages give none. */
export function eventFromMessage(raw: unknown): AdapterEvent | null {
  if (typeof raw !== "string") {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  const message = asRecord(parsed);
  const type = typeof message?.type === "string" ? message.type : "";
  const transcript = typeof message?.transcript === "string" ? message.transcript.trim() : "";
  switch (type) {
    case "input_audio_buffer.speech_started":
      return { type: "listening" };
    case "input_audio_buffer.speech_stopped":
      // Not "thinking": with turn detection the provider may still be waiting for the person to
      // go on, and showing a thinking state here made a short pause look like the end of a turn.
      return null;
    case "response.created":
      return { type: "thinking" };
    case "conversation.item.input_audio_transcription.completed":
      return transcript === ""
        ? null
        : { type: "transcript", speaker: "user", text: transcript, source: "voice" };
    case "response.output_audio_transcript.delta":
    case "response.audio_transcript.delta":
      return { type: "speaking" };
    case "response.output_audio_transcript.done":
    case "response.audio_transcript.done":
      return transcript === ""
        ? null
        : { type: "transcript", speaker: "assistant", text: transcript, source: "assistant" };
    case "response.done":
      return { type: "listening" };
    case "error":
      // Never repeat the provider's own message: it can echo request details.
      return { type: "error", code: "connection", message: "The voice service reported a problem." };
    default:
      return null;
  }
}

export function createRealtimeAdapter(options: RealtimeAdapterOptions = {}): VoiceAdapter {
  const api = options.api ?? realtimeVoiceApi;

  let env: RtcEnvironment | null = null;
  let listener: AdapterListener | null = null;
  let sessionId: string | null = null;
  let opening: AbortController | null = null;
  let peer: RtcPeer | null = null;
  let channel: RtcChannel | null = null;
  let stream: RtcStream | null = null;
  let audio: RtcAudio | null = null;
  let limitTimer: unknown = null;
  // One reply at a time. `active` is true from response.created to response.done. `suppress` drops
  // the leftovers of a reply the person talked over, so they cannot reappear after the cancel.
  // `deferred` holds a typed message's reply request that arrived while a reply was running.
  let active = false;
  let suppress = false;
  let deferred = false;

  const emit = (event: AdapterEvent) => listener?.(event);

  function release() {
    if (limitTimer !== null) {
      env?.clearTimer(limitTimer);
      limitTimer = null;
    }
    channel?.close();
    peer?.close();
    for (const track of stream?.getTracks() ?? []) {
      track.stop();
    }
    audio?.pause();
    if (audio !== null) {
      audio.srcObject = null;
    }
    channel = null;
    peer = null;
    stream = null;
    audio = null;
    active = false;
    suppress = false;
    deferred = false;
  }

  function track(raw: unknown): { drop: boolean } {
    const type = typeof raw === "string" ? (asRecord(safeParse(raw))?.type ?? "") : "";
    switch (type) {
      case "response.created":
        active = true;
        suppress = false;
        break;
      case "input_audio_buffer.speech_started":
        // The provider cancels the running reply when the person speaks again.
        if (active) {
          suppress = true;
        }
        break;
      case "response.done":
        active = false;
        suppress = false;
        if (deferred) {
          deferred = false;
          send({ type: "response.create" });
        }
        break;
      case "response.output_audio_transcript.delta":
      case "response.audio_transcript.delta":
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done":
        return { drop: suppress };
      default:
        break;
    }
    return { drop: false };
  }

  function send(payload: Record<string, unknown>) {
    if (channel !== null && channel.readyState === "open") {
      channel.send(JSON.stringify(payload));
    }
  }

  return {
    name: "OpenAI live voice (development build)",
    isMock: false,
    playsAudio: true,
    hearsUser: true,
    audioDisclosure: REALTIME_DISCLOSURE,

    async connect(connectOptions, nextListener) {
      env = options.env ?? browserEnvironment();
      listener = nextListener;
      const controller = new AbortController();
      opening = controller;
      let id: string | null = null;
      try {
        const info = await api.create(controller.signal);
        id = info.session_id;
        sessionId = id;
        // A microphone is asked for only after the server has agreed to a session.
        let localStream: RtcStream | null = null;
        if (connectOptions.microphone) {
          try {
            localStream = await env.getUserMedia({ audio: true });
          } catch (error) {
            throw microphoneError(error);
          }
        }
        if (controller.signal.aborted) {
          throw new VoiceConnectionError("connection", "The session was closed.");
        }
        stream = localStream;
        const grant = await api.realtime(id, controller.signal);
        // The secret lives only in this block: one request, then it goes out of scope.
        const connection = env.createPeer();
        peer = connection;
        const player = env.createAudio();
        player.autoplay = true;
        audio = player;
        connection.ontrack = (event) => {
          player.srcObject = event.streams[0] ?? null;
        };
        for (const track of localStream?.getTracks() ?? []) {
          connection.addTrack(track, localStream as RtcStream);
        }
        const events = connection.createDataChannel(EVENTS_CHANNEL);
        channel = events;
        events.onmessage = (message) => {
          const { drop } = track(message.data);
          const event = drop ? null : eventFromMessage(message.data);
          if (event !== null) {
            emit(event);
          }
        };
        connection.onconnectionstatechange = () => {
          if (connection.connectionState === "failed" || connection.connectionState === "disconnected") {
            emit({ type: "error", code: "connection", message: "Lost the voice connection." });
          }
        };
        const offer = await connection.createOffer();
        await connection.setLocalDescription(offer);
        const response = await env.fetchText(OPENAI_CALLS_URL, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${grant.client_secret}`,
            "Content-Type": "application/sdp",
          },
          body: offer.sdp ?? "",
          signal: controller.signal,
        });
        if (!response.ok) {
          // The status is not shown: the reason is the provider's, not ours to repeat.
          throw new VoiceConnectionError("unavailable", "The voice service did not accept the connection.");
        }
        await connection.setRemoteDescription({ type: "answer", sdp: await response.text() });
        if (controller.signal.aborted) {
          throw new VoiceConnectionError("connection", "The session was closed.");
        }
        // The server's time limit ends the session here too, because the audio does not pass
        // through the server.
        limitTimer = env.setTimer(() => {
          emit({ type: "error", code: "session_expired", message: "The voice session has ended. Start a new one." });
          release();
        }, grant.max_seconds * 1000);
        emit({ type: "listening" });
      } catch (error) {
        const failedId = id;
        release();
        sessionId = null;
        listener = null;
        if (failedId !== null) {
          void api.end(failedId).catch(() => undefined);
        }
        if (error instanceof VoiceConnectionError) {
          throw error;
        }
        if (controller.signal.aborted) {
          throw new VoiceConnectionError("connection", "The session was closed.");
        }
        throw connectionErrorFor(error);
      } finally {
        if (opening === controller) {
          opening = null;
        }
      }
    },

    disconnect() {
      opening?.abort();
      opening = null;
      release();
      const id = sessionId;
      sessionId = null;
      listener = null;
      if (id !== null) {
        void api.end(id).catch(() => undefined);
      }
    },

    setMuted(muted) {
      for (const track of stream?.getTracks() ?? []) {
        track.enabled = !muted;
      }
    },

    interrupt() {
      if (active) {
        suppress = true;
      }
      deferred = false;
      send({ type: "response.cancel" });
      send({ type: "output_audio_buffer.clear" });
      emit({ type: "listening" });
    },

    sendText(text) {
      const trimmed = text.trim();
      if (trimmed === "") {
        return;
      }
      send({
        type: "conversation.item.create",
        item: { type: "message", role: "user", content: [{ type: "input_text", text: trimmed }] },
      });
      if (active) {
        deferred = true; // one reply at a time: ask again when the running one is done
      } else {
        send({ type: "response.create" });
      }
      emit({ type: "transcript", speaker: "user", text: trimmed, source: "typed" });
      emit({ type: "thinking" });
    },
  };
}
