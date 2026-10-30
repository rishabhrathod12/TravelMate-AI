/**
 * Client for the backend typed-chat endpoint (docs/VOICE_ASSISTANT_PLAN.md, V5 front end).
 *
 * The server keeps nothing between turns: each call sends what was typed and the draft so far, and
 * gets back the new draft, a reply, and a validated trip request once everything is known. No
 * language model is connected; the server answers with a labelled development stand-in.
 */

import type { TripRequest } from "../contracts/types";
import { apiBaseUrl } from "./health";

export type TurnStatus = "NEEDS_INFO" | "CONFLICT" | "READY_FOR_REVIEW" | "NOT_UNDERSTOOD";

/** The draft is opaque to the browser: it is only sent back as received. */
export type ChatDraft = Record<string, unknown>;

export interface ChatTurn {
  status: TurnStatus;
  reply: string;
  draft: ChatDraft;
  tripRequest: TripRequest | null;
  modelKind: string;
  modelNotice: string;
}

/** A failed call. `status` is null when the server could not be reached at all. */
export class ChatApiError extends Error {
  readonly status: number | null;
  readonly detail: string | null;

  constructor(status: number | null, detail: string | null) {
    super(status === null ? "The server could not be reached" : `The server answered HTTP ${status}`);
    this.name = "ChatApiError";
    this.status = status;
    this.detail = detail;
  }
}

const STATUSES: readonly string[] = ["NEEDS_INFO", "CONFLICT", "READY_FOR_REVIEW", "NOT_UNDERSTOOD"];

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTripRequest(value: unknown): value is TripRequest {
  return (
    isObject(value) &&
    (value.trip_type === "ONE_WAY" || value.trip_type === "ROUND_TRIP") &&
    isObject(value.origin) &&
    typeof value.origin.name === "string" &&
    isObject(value.destination) &&
    typeof value.destination.name === "string" &&
    typeof value.departure_date === "string" &&
    (value.return_date === null || typeof value.return_date === "string") &&
    Array.isArray(value.travellers) &&
    value.travellers.length > 0 &&
    (value.preferences === null || typeof value.preferences === "string")
  );
}

function readTurn(body: unknown): ChatTurn | null {
  if (
    !isObject(body) ||
    typeof body.status !== "string" ||
    !STATUSES.includes(body.status) ||
    typeof body.reply !== "string" ||
    !isObject(body.draft) ||
    !isObject(body.model) ||
    typeof body.model.kind !== "string" ||
    typeof body.model.notice !== "string"
  ) {
    return null;
  }
  const tripRequest = body.trip_request ?? null;
  if (tripRequest !== null && !isTripRequest(tripRequest)) {
    return null;
  }
  return {
    status: body.status as TurnStatus,
    reply: body.reply,
    draft: body.draft,
    tripRequest,
    modelKind: body.model.kind,
    modelNotice: body.model.notice,
  };
}

async function problemDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (isObject(body) && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON: there is no detail to show.
  }
  return null;
}

export async function sendChatTurn(
  message: string,
  draft: ChatDraft | null,
  signal?: AbortSignal,
): Promise<ChatTurn> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/chat/turns`, {
      method: "POST",
      signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ message, draft }),
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new ChatApiError(null, null);
  }
  if (!response.ok) {
    throw new ChatApiError(response.status, await problemDetail(response));
  }
  const turn = readTurn(await response.json());
  if (turn === null) {
    throw new ChatApiError(response.status, "The server's answer did not have the expected shape.");
  }
  return turn;
}
