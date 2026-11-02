/**
 * Client for the backend planning API (docs/ARCHITECTURE.md section 7; plan M8, M11).
 *
 * It creates a trip, starts a run, reads it and sends the traveller's choice of options. Every
 * answer is checked for its shape before it is used, and a failure carries the server's Problem
 * Details `detail` and `code`, which are fixed wording written to be shown. The server is the only
 * source of options, prices and provenance: nothing here invents them.
 *
 * The API is development-only (no real authentication yet, PRD Q4): it acts for one configured
 * principal and the server does not start it in production.
 */

import type {
  CostEstimate,
  HotelOption,
  Itinerary,
  TransportOption,
  TripRequest,
} from "../contracts/types";
import { apiBaseUrl } from "./health";

export type RunStatus =
  | "pending"
  | "running"
  | "awaiting_clarification"
  | "awaiting_selection"
  | "completed"
  | "failed"
  | "stopped_limit";

const RUN_STATUSES: readonly string[] = [
  "pending",
  "running",
  "awaiting_clarification",
  "awaiting_selection",
  "completed",
  "failed",
  "stopped_limit",
];

/** The ids the traveller may choose from, as the server sent them while the run waits. */
export interface ChoiceIds {
  transport: string[];
  returnTransport: string[];
  hotels: string[];
}

export interface Research {
  transport: TransportOption[];
  returnTransport: TransportOption[];
  hotels: HotelOption[];
}

export interface PlanningRun {
  runId: string;
  tripId: string;
  status: RunStatus;
  /** Set while the run waits for a choice. */
  choices: ChoiceIds | null;
  research: Research | null;
  /** Set once the run has finished and priced the chosen options. */
  estimate: CostEstimate | null;
  /** The server's fixed-wording note when a run failed. */
  error: string | null;
  /** The questions the server asks while the run waits for clarification; empty otherwise. */
  questions: string[];
  /** What was chosen, once the run has finished. */
  selected: Selection | null;
  /** The itinerary draft the run wrote, if any. It is a draft, not a verified plan. */
  itinerary: Itinerary | null;
  itineraryWarnings: string[];
}

export interface Selection {
  transportId: string | null;
  returnTransportId: string | null;
  hotelId: string | null;
}

/** A failed call. `status` is null when the server could not be reached at all. */
export class PlanningApiError extends Error {
  readonly status: number | null;
  readonly detail: string | null;
  readonly code: string | null;

  constructor(status: number | null, detail: string | null, code: string | null = null) {
    super(status === null ? "The server could not be reached" : `The server answered HTTP ${status}`);
    this.name = "PlanningApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] | null {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? (value as string[])
    : null;
}

function readChoices(value: unknown): ChoiceIds | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }
  if (!isObject(value)) {
    return undefined;
  }
  const transport = stringList(value.transport);
  const returnTransport = stringList(value.return_transport);
  const hotels = stringList(value.hotels);
  if (transport === null || returnTransport === null || hotels === null) {
    return undefined;
  }
  return { transport, returnTransport, hotels };
}

function optionList<T extends { id: string }>(value: unknown): T[] | null {
  if (value === undefined || value === null) {
    return [];
  }
  if (!isObject(value) || !Array.isArray(value.options)) {
    return null;
  }
  const options: unknown[] = value.options;
  return options.every((o) => isObject(o) && typeof o.id === "string" && isObject(o.source))
    ? (options as T[])
    : null;
}

function readResearch(value: unknown): Research | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }
  if (!isObject(value)) {
    return undefined;
  }
  const transport = optionList<TransportOption>(value.transport);
  const returnTransport = optionList<TransportOption>(value.return_transport);
  const hotels = optionList<HotelOption>(value.hotels);
  if (transport === null || returnTransport === null || hotels === null) {
    return undefined;
  }
  return { transport, returnTransport, hotels };
}

function readEstimate(summary: unknown): CostEstimate | null | undefined {
  if (summary === null || summary === undefined) {
    return null;
  }
  if (!isObject(summary)) {
    return undefined;
  }
  const estimate = summary.estimate;
  if (estimate === null || estimate === undefined) {
    return null;
  }
  return isObject(estimate) &&
    typeof estimate.currency === "string" &&
    Array.isArray(estimate.lines) &&
    Array.isArray(estimate.missing_items)
    ? (estimate as unknown as CostEstimate)
    : undefined;
}

function readQuestions(waitingFor: unknown): string[] {
  if (!isObject(waitingFor) || waitingFor.kind !== "CLARIFICATION") {
    return [];
  }
  return stringList(waitingFor.questions) ?? [];
}

function readSummaryParts(summary: unknown): {
  selected: Selection | null;
  itinerary: Itinerary | null;
  itineraryWarnings: string[];
} | null {
  if (summary === null || summary === undefined) {
    return { selected: null, itinerary: null, itineraryWarnings: [] };
  }
  if (!isObject(summary)) {
    return null;
  }
  const picked = summary.selection;
  let selected: Selection | null = null;
  if (isObject(picked)) {
    const text = (value: unknown) => (typeof value === "string" ? value : null);
    selected = {
      transportId: text(picked.transport_id),
      returnTransportId: text(picked.return_transport_id),
      hotelId: text(picked.hotel_id),
    };
  }
  const draft = summary.itinerary;
  let itinerary: Itinerary | null = null;
  if (draft !== null && draft !== undefined) {
    if (!isObject(draft) || !Array.isArray(draft.days)) {
      return null;
    }
    itinerary = draft as unknown as Itinerary;
  }
  const warnings = stringList(summary.itinerary_warnings);
  if (warnings === null) {
    return null;
  }
  return { selected, itinerary, itineraryWarnings: warnings };
}

function readRun(body: unknown): PlanningRun | null {
  if (
    !isObject(body) ||
    typeof body.run_id !== "string" ||
    typeof body.trip_id !== "string" ||
    typeof body.status !== "string" ||
    !RUN_STATUSES.includes(body.status)
  ) {
    return null;
  }
  const choices = readChoices(body.waiting_for);
  const research = readResearch(body.research);
  const estimate = readEstimate(body.summary);
  const parts = readSummaryParts(body.summary);
  if (
    choices === undefined ||
    research === undefined ||
    estimate === undefined ||
    parts === null
  ) {
    return null;
  }
  const error = body.error;
  if (error !== null && error !== undefined && typeof error !== "string") {
    return null;
  }
  return {
    runId: body.run_id,
    tripId: body.trip_id,
    status: body.status as RunStatus,
    choices,
    research,
    estimate,
    error: error ?? null,
    questions: readQuestions(body.waiting_for),
    selected: parts.selected,
    itinerary: parts.itinerary,
    itineraryWarnings: parts.itineraryWarnings,
  };
}

async function problem(response: Response): Promise<PlanningApiError> {
  try {
    const body: unknown = await response.json();
    if (isObject(body)) {
      return new PlanningApiError(
        response.status,
        typeof body.detail === "string" ? body.detail : null,
        typeof body.code === "string" ? body.code : null,
      );
    }
  } catch {
    // Not JSON: there is no detail to show.
  }
  return new PlanningApiError(response.status, null);
}

export async function call(
  path: string,
  method: "GET" | "POST",
  payload: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1${path}`, {
      method,
      signal,
      headers:
        payload === undefined
          ? { Accept: "application/json" }
          : { Accept: "application/json", "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new PlanningApiError(null, null);
  }
  if (!response.ok) {
    throw await problem(response);
  }
  return response.json();
}

function expectRun(body: unknown, status: number | null = 200): PlanningRun {
  const run = readRun(body);
  if (run === null) {
    throw new PlanningApiError(status, "The server's answer did not have the expected shape.");
  }
  return run;
}

/** The request as the trip's draft: the server keeps what the traveller gave it. */
export function draftFromRequest(request: TripRequest): Record<string, unknown> {
  return {
    origin: request.origin.name,
    destination: request.destination.name,
    trip_type: request.trip_type,
    departure_date: request.departure_date,
    return_date: request.return_date,
    traveller_count: request.travellers.length,
    preferences: request.preferences,
  };
}

/**
 * Creates a trip. `rooms` is an explicit input, never a default: how many rooms a party needs is
 * not decided (PRD Q14).
 */
export async function createTrip(
  title: string,
  request: TripRequest,
  rooms: number | null,
  signal?: AbortSignal,
): Promise<string> {
  const body = await call("/trips", "POST", { title, draft: draftFromRequest(request), rooms }, signal);
  if (!isObject(body) || typeof body.id !== "string") {
    throw new PlanningApiError(201, "The server's answer did not have the expected shape.");
  }
  return body.id;
}

export async function startRun(tripId: string, signal?: AbortSignal): Promise<PlanningRun> {
  return expectRun(await call(`/trips/${encodeURIComponent(tripId)}/runs`, "POST", undefined, signal), 202);
}

export async function getRun(runId: string, signal?: AbortSignal): Promise<PlanningRun> {
  return expectRun(await call(`/runs/${encodeURIComponent(runId)}`, "GET", undefined, signal));
}

export async function chooseOptions(
  runId: string,
  selection: Selection,
  signal?: AbortSignal,
): Promise<PlanningRun> {
  const payload = {
    transport_id: selection.transportId,
    return_transport_id: selection.returnTransportId,
    hotel_id: selection.hotelId,
  };
  return expectRun(
    await call(`/runs/${encodeURIComponent(runId)}/selections`, "POST", payload, signal),
    202,
  );
}

const WORKING: readonly RunStatus[] = ["pending", "running"];

/** True while the server is still working, so the caller should read the run again shortly. */
export function isWorking(run: PlanningRun): boolean {
  return WORKING.includes(run.status);
}

/** The trip's draft as the server holds it: what the traveller gave, possibly incomplete. */
export type TripDraft = Record<string, unknown>;

export async function getTripDraft(tripId: string, signal?: AbortSignal): Promise<TripDraft> {
  const body = await call(`/trips/${encodeURIComponent(tripId)}`, "GET", undefined, signal);
  if (!isObject(body) || !isObject(body.draft)) {
    throw new PlanningApiError(200, "The server's answer did not have the expected shape.");
  }
  return body.draft;
}

/** Answers the server's questions by sending the corrected draft. The run then resumes. */
export async function answerClarification(
  runId: string,
  draft: TripDraft,
  signal?: AbortSignal,
): Promise<PlanningRun> {
  return expectRun(
    await call(`/runs/${encodeURIComponent(runId)}/clarifications`, "POST", { draft }, signal),
    202,
  );
}

export interface SavedItinerary {
  version: number;
  createdBy: string;
  itinerary: Itinerary;
}

function expectItinerary(body: unknown, status: number): SavedItinerary {
  if (
    !isObject(body) ||
    typeof body.version !== "number" ||
    typeof body.created_by !== "string" ||
    !isObject(body.itinerary) ||
    !Array.isArray(body.itinerary.days)
  ) {
    throw new PlanningApiError(status, "The server's answer did not have the expected shape.");
  }
  return {
    version: body.version,
    createdBy: body.created_by,
    itinerary: body.itinerary as unknown as Itinerary,
  };
}

export async function saveItineraryVersion(
  tripId: string,
  itinerary: Itinerary,
  signal?: AbortSignal,
): Promise<SavedItinerary> {
  const body = await call(
    `/trips/${encodeURIComponent(tripId)}/itinerary/versions`,
    "POST",
    { itinerary },
    signal,
  );
  return expectItinerary(body, 201);
}
