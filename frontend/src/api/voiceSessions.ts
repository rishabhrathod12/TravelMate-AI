/**
 * Client for the backend voice-session endpoints (docs/VOICE_ASSISTANT_PLAN.md, Step B).
 *
 * A session carries no audio and there is no voice vendor: these calls only open, read, touch and
 * end a short-lived server-side session. Nothing here sends speech, text or transcripts. The
 * session ID is an opaque identifier; the server checks ownership on every call.
 */

import { apiBaseUrl } from "./health";

export interface VoiceSessionInfo {
  session_id: string;
  expires_at: string;
  max_seconds: number;
  idle_timeout_seconds: number;
  provider: null;
  notice: string;
}

/** A failed call. `status` is null when the server could not be reached at all. */
export class VoiceApiError extends Error {
  readonly status: number | null;
  /** The server's own explanation, from its Problem Details body, if it sent one. */
  readonly detail: string | null;

  constructor(status: number | null, detail: string | null) {
    super(status === null ? "The server could not be reached" : `The server answered HTTP ${status}`);
    this.name = "VoiceApiError";
    this.status = status;
    this.detail = detail;
  }
}

function isSessionInfo(value: unknown): value is VoiceSessionInfo {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const v = value as Record<string, unknown>;
  return (
    typeof v.session_id === "string" &&
    v.session_id.length > 0 &&
    typeof v.expires_at === "string" &&
    typeof v.max_seconds === "number" &&
    typeof v.idle_timeout_seconds === "number" &&
    v.provider === null &&
    typeof v.notice === "string"
  );
}

async function problemDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null) {
      const detail = (body as Record<string, unknown>).detail;
      return typeof detail === "string" ? detail : null;
    }
  } catch {
    // Not JSON: there is no detail to show.
  }
  return null;
}

async function send(path: string, method: string, signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/voice/sessions${path}`, {
      method,
      signal,
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new VoiceApiError(null, null);
  }
  if (!response.ok) {
    throw new VoiceApiError(response.status, await problemDetail(response));
  }
  return response;
}

async function readInfo(response: Response): Promise<VoiceSessionInfo> {
  const body: unknown = await response.json();
  if (!isSessionInfo(body)) {
    throw new VoiceApiError(response.status, "The server's answer did not have the expected shape.");
  }
  return body;
}

const pathFor = (sessionId: string) => `/${encodeURIComponent(sessionId)}`;

export async function createVoiceSession(signal?: AbortSignal): Promise<VoiceSessionInfo> {
  return readInfo(await send("", "POST", signal));
}

export async function readVoiceSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<VoiceSessionInfo> {
  return readInfo(await send(pathFor(sessionId), "GET", signal));
}

/** Tell the server the user did something, so the idle timer restarts. */
export async function recordVoiceActivity(
  sessionId: string,
  signal?: AbortSignal,
): Promise<VoiceSessionInfo> {
  return readInfo(await send(`${pathFor(sessionId)}/activity`, "POST", signal));
}

export async function endVoiceSession(sessionId: string, signal?: AbortSignal): Promise<void> {
  await send(pathFor(sessionId), "DELETE", signal);
}

/** The operations the session adapter needs, so tests can supply a fake. */
export interface VoiceSessionApi {
  create(signal?: AbortSignal): Promise<VoiceSessionInfo>;
  read(sessionId: string, signal?: AbortSignal): Promise<VoiceSessionInfo>;
  activity(sessionId: string, signal?: AbortSignal): Promise<VoiceSessionInfo>;
  end(sessionId: string, signal?: AbortSignal): Promise<void>;
}

export const voiceSessionApi: VoiceSessionApi = {
  create: createVoiceSession,
  read: readVoiceSession,
  activity: recordVoiceActivity,
  end: endVoiceSession,
};
