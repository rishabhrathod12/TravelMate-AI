/**
 * Client for the booking intent and approval API (ARCHITECTURE section 7; plan M10, M11).
 *
 * Booking itself is switched off. Creating an intent records one quoted option and the exact terms
 * a person was shown; approving records their agreement to exactly those terms for a short time.
 * Neither books anything or takes a payment, and this client has no way to call `execute`: that
 * route always refuses, so no screen needs it.
 *
 * Every answer is checked for its shape. An answer that says booking is enabled is refused: the
 * screens must never suggest something the server says is not so.
 */

import type { Quote } from "../contracts/types";
import { PlanningApiError, call, isObject } from "./planning";

export type QuoteCategory = "TRANSPORT" | "RETURN_TRANSPORT" | "HOTEL";

export type IntentStatus =
  | "DRAFT"
  | "QUOTED"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "REVALIDATION"
  | "BOOKING"
  | "CONFIRMED"
  | "FAILED"
  | "NEEDS_REVIEW"
  | "CANCELLED"
  | "EXPIRED";

const STATUSES: readonly string[] = [
  "DRAFT",
  "QUOTED",
  "AWAITING_APPROVAL",
  "APPROVED",
  "REVALIDATION",
  "BOOKING",
  "CONFIRMED",
  "FAILED",
  "NEEDS_REVIEW",
  "CANCELLED",
  "EXPIRED",
];

export interface Approval {
  id: string;
  approvedAt: string;
  expiresAt: string;
  quoteContentHash: string;
}

export interface BookingIntent {
  id: string;
  tripId: string;
  status: IntentStatus;
  category: QuoteCategory;
  quote: Quote;
  /** The fingerprint of the terms on screen. Approval is refused if it is not the current one. */
  quoteContentHash: string;
  travellers: number;
  approval: Approval | null;
  /** The server's own wording about what approving does and does not do. */
  notice: string;
}

function readApproval(value: unknown): Approval | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }
  if (
    !isObject(value) ||
    typeof value.id !== "string" ||
    typeof value.approved_at !== "string" ||
    typeof value.expires_at !== "string" ||
    typeof value.quote_content_hash !== "string"
  ) {
    return undefined;
  }
  return {
    id: value.id,
    approvedAt: value.approved_at,
    expiresAt: value.expires_at,
    quoteContentHash: value.quote_content_hash,
  };
}

function expectIntent(body: unknown, status: number): BookingIntent {
  const bad = () => new PlanningApiError(status, "The server's answer did not have the expected shape.");
  if (
    !isObject(body) ||
    typeof body.id !== "string" ||
    typeof body.trip_id !== "string" ||
    typeof body.status !== "string" ||
    !STATUSES.includes(body.status) ||
    typeof body.category !== "string" ||
    !isObject(body.quote) ||
    typeof body.quote_content_hash !== "string" ||
    body.quote_content_hash.length !== 64 ||
    typeof body.travellers !== "number" ||
    typeof body.notice !== "string"
  ) {
    throw bad();
  }
  if (body.booking_enabled !== false) {
    // The one thing this client never accepts: a server claiming bookings can happen.
    throw new PlanningApiError(status, "The server did not say that booking is switched off, so this screen will not use its answer.");
  }
  const approval = readApproval(body.approval);
  if (approval === undefined) {
    throw bad();
  }
  return {
    id: body.id,
    tripId: body.trip_id,
    status: body.status as IntentStatus,
    category: body.category as QuoteCategory,
    quote: body.quote as unknown as Quote,
    quoteContentHash: body.quote_content_hash,
    travellers: body.travellers,
    approval,
    notice: body.notice,
  };
}

/**
 * Records a booking intent for one researched option. The same `idempotencyKey` with the same
 * request returns the first intent, so a repeated click never makes a second one.
 */
export async function createIntent(
  tripId: string,
  category: QuoteCategory,
  optionId: string,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<BookingIntent> {
  const body = await call(
    `/trips/${encodeURIComponent(tripId)}/booking-intents`,
    "POST",
    { category, option_id: optionId, idempotency_key: idempotencyKey },
    signal,
  );
  return expectIntent(body, 201);
}

export async function getIntent(intentId: string, signal?: AbortSignal): Promise<BookingIntent> {
  return expectIntent(
    await call(`/booking-intents/${encodeURIComponent(intentId)}`, "GET", undefined, signal),
    200,
  );
}

/**
 * Records the person's agreement to the terms they are looking at. `displayedHash` must be the
 * hash of those terms; the server refuses it if the terms have since changed.
 */
export async function approveIntent(
  intentId: string,
  displayedHash: string,
  signal?: AbortSignal,
): Promise<BookingIntent> {
  return expectIntent(
    await call(
      `/booking-intents/${encodeURIComponent(intentId)}/approvals`,
      "POST",
      { quote_content_hash: displayedHash },
      signal,
    ),
    201,
  );
}
