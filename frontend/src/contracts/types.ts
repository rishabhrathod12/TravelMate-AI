/**
 * TypeScript shapes of the backend domain models as they appear in JSON.
 *
 * They mirror the Pydantic models in `backend/app/domain/`. They are written by
 * hand for now; a generated client (from the OpenAPI schema, Milestone 8) will
 * replace them. Only `HealthResponse` is returned by a real endpoint today.
 */

export type Provenance = "LIVE" | "CACHED_LIVE" | "MOCK";
export type AvailabilityStatus = "AVAILABLE" | "UNAVAILABLE" | "UNKNOWN";
export type TransportMode = "FLIGHT" | "TRAIN" | "BUS" | "ROAD";
export type TripType = "ONE_WAY" | "ROUND_TRIP";
export type CostLineKind =
  | "TRANSPORT"
  | "ACCOMMODATION"
  | "LOCAL_TRANSPORT"
  | "CONTINGENCY"
  | "TAXES_AND_FEES";

/** Integer minor units (for example paise for INR) plus a currency code. */
export interface Money {
  amount_minor: number;
  currency: string;
}

export interface SourceMetadata {
  provenance: Provenance;
  provider_name: string;
  /** ISO 8601 timestamp in UTC. */
  retrieved_at: string;
  freshness_window_seconds: number;
}

export interface Location {
  name: string;
}

export interface Traveller {
  age: number | null;
}

export interface TripRequest {
  trip_type: TripType;
  origin: Location;
  destination: Location;
  /** Calendar date, YYYY-MM-DD, no time zone. */
  departure_date: string;
  return_date: string | null;
  travellers: Traveller[];
  preferences: string | null;
}

interface OptionBase {
  id: string;
  source: SourceMetadata;
  availability: AvailabilityStatus;
  cancellation_terms: string | null;
}

/** Facts that exist for one transport mode only. It always matches the option's `mode`. */
export type ModeDetails =
  | { kind: "FLIGHT"; cabin_class: string | null }
  | { kind: "TRAIN"; travel_class: string | null }
  | { kind: "BUS"; seat_type: string | null };

export interface TransportOption extends OptionBase {
  mode: TransportMode;
  origin: Location;
  destination: Location;
  departs_at: string;
  arrives_at: string;
  stops: number | null;
  price: Money | null;
  /** The operator and service as the provider names them. Fictional in MOCK data. */
  operator_name: string | null;
  service_label: string | null;
  details: ModeDetails | null;
}

export interface HotelOption extends OptionBase {
  name: string;
  location: Location;
  nightly_rate: Money | null;
}

export interface Fee {
  label: string;
  amount: Money;
}

/**
 * What a quoted price covers (the owner's answer to PRD Q12): a transport fare is per traveller, a
 * hotel price is per room per night. Mirrors `PriceBasis` in `backend/app/domain/quote.py`.
 */
export type PriceBasis = "PER_TRAVELLER" | "PER_ROOM_NIGHT";

export interface Quote {
  id: string;
  option_id: string;
  price: Money;
  price_basis: PriceBasis;
  fees: Fee[];
  availability: AvailabilityStatus;
  cancellation_terms: string | null;
  valid_until: string;
  source: SourceMetadata;
}

export interface CostLine {
  kind: CostLineKind;
  description: string;
  amount: Money;
  provenance: Provenance;
}

/** The backend computes the total from the lines; it is not part of the JSON. */
export interface CostEstimate {
  currency: string;
  lines: CostLine[];
  missing_items: string[];
}

export interface ItineraryItem {
  title: string;
  description: string | null;
  option_id: string | null;
}

export interface ItineraryDay {
  day_number: number;
  items: ItineraryItem[];
}

export interface Itinerary {
  days: ItineraryDay[];
  notes: string | null;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

/**
 * A request to write a day-by-day itinerary for one place (ADR 0004). It mirrors
 * `ItineraryRequest` in `backend/app/domain/trip.py`: there is no origin and no transport.
 * `days` counts calendar days including the first.
 */
export interface ItineraryRequest {
  destination: Location;
  start_date: string;
  days: number;
  travellers: number | null;
  preferences: string | null;
}

/**
 * Where a line of an itinerary came from. It is not a provenance label: `LIVE`, `CACHED_LIVE`
 * and `MOCK` describe provider data, and an itinerary line is never provider data.
 * - `SCRIPTED_SAMPLE`: fixed placeholder text written in code, not by any model.
 * - `AI_SUGGESTION`: a suggestion from a language model, "AI suggestion, not verified". No model
 *   is connected yet, so nothing carries this label today.
 */
export type SuggestionLabel = "SCRIPTED_SAMPLE" | "AI_SUGGESTION";

/** One line of a plan. It has no field for a price, time, availability or booking. */
export interface PlanItem {
  title: string;
  description: string | null;
}

export interface PlanDay {
  day_number: number;
  items: PlanItem[];
}

export interface SuggestedPlan {
  days: PlanDay[];
  notes: string | null;
}

/**
 * The server's answer to a plan request. `source` says where the plan came from and is decided by
 * the server's own configuration, never by the model: `SCRIPTED_SAMPLE` is fixed placeholder text,
 * `AI_SUGGESTION` is a language model's suggestion, not verified. `notice` is the server's own
 * sentence about it and is shown as received.
 */
export interface PlanResponse {
  source: SuggestionLabel;
  notice: string;
  plan: SuggestedPlan;
}
