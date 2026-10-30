/**
 * Client for the backend typed-chat endpoint (docs/VOICE_ASSISTANT_PLAN.md, V5 front end).
 *
 * The server keeps nothing between turns: each call sends what was typed and the draft so far, and
 * gets back the new draft, a reply, and a validated trip request once everything is known. No
 * language model is connected; the server answers with a labelled development stand-in.
 */

import type {
  ItineraryRequest,
  PlanDay,
  PlanResponse,
  SuggestedPlan,
  TripRequest,
} from "../contracts/types";
import { apiBaseUrl } from "./health";

export type TurnStatus = "NEEDS_INFO" | "CONFIRM_DATES" | "CONFLICT" | "READY_FOR_REVIEW" | "NOT_UNDERSTOOD";

/** The draft is opaque to the browser: it is only sent back as received. */
export type ChatDraft = Record<string, unknown>;

export interface ChatTurn {
  status: TurnStatus;
  reply: string;
  draft: ChatDraft;
  tripRequest: TripRequest | null;
  itineraryRequest: ItineraryRequest | null;
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

const STATUSES: readonly string[] = ["NEEDS_INFO", "CONFIRM_DATES", "CONFLICT", "READY_FOR_REVIEW", "NOT_UNDERSTOOD"];

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

function isItineraryRequest(value: unknown): value is ItineraryRequest {
  return (
    isObject(value) &&
    isObject(value.destination) &&
    typeof value.destination.name === "string" &&
    typeof value.start_date === "string" &&
    typeof value.days === "number" &&
    Number.isInteger(value.days) &&
    value.days >= 1 &&
    (value.travellers === null || typeof value.travellers === "number") &&
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
  const itineraryRequest = body.itinerary_request ?? null;
  if (itineraryRequest !== null && !isItineraryRequest(itineraryRequest)) {
    return null;
  }
  return {
    status: body.status as TurnStatus,
    reply: body.reply,
    draft: body.draft,
    tripRequest,
    itineraryRequest,
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

function isPlanDay(value: unknown): value is PlanDay {
  return (
    isObject(value) &&
    typeof value.day_number === "number" &&
    Number.isInteger(value.day_number) &&
    value.day_number >= 1 &&
    Array.isArray(value.items) &&
    value.items.length > 0 &&
    value.items.every(
      (item: unknown) =>
        isObject(item) &&
        typeof item.title === "string" &&
        item.title !== "" &&
        (item.description === null ||
          item.description === undefined ||
          typeof item.description === "string"),
    )
  );
}

function readPlan(body: unknown): PlanResponse | null {
  if (
    !isObject(body) ||
    (body.source !== "SCRIPTED_SAMPLE" && body.source !== "AI_SUGGESTION") ||
    typeof body.notice !== "string" ||
    !isObject(body.plan) ||
    !Array.isArray(body.plan.days) ||
    body.plan.days.length === 0 ||
    !body.plan.days.every(isPlanDay)
  ) {
    return null;
  }
  const notes = body.plan.notes;
  if (notes !== null && notes !== undefined && typeof notes !== "string") {
    return null;
  }
  const plan: SuggestedPlan = {
    days: body.plan.days.map((day) => ({
      day_number: day.day_number,
      items: day.items.map((item) => ({
        title: item.title,
        description: item.description ?? null,
      })),
    })),
    notes: notes ?? null,
  };
  return { source: body.source, notice: body.notice, plan };
}

/**
 * Asks the server to write the plan for an itinerary request. The server decides whether a real
 * model or the scripted sample answers, and says which in `source`.
 */
export async function requestPlan(
  request: ItineraryRequest,
  signal?: AbortSignal,
): Promise<PlanResponse> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/chat/plans`, {
      method: "POST",
      signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ itinerary_request: request }),
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
  const plan = readPlan(await response.json());
  if (plan === null) {
    throw new ChatApiError(response.status, "The server's answer did not have the expected shape.");
  }
  return plan;
}
