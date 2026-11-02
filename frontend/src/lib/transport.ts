/**
 * Pure helpers for showing and comparing transport options. They only read option data: no
 * provider, no network, no booking. Mode-specific facts are shown only for the modes they fit.
 */

import type { Money, Quote, TransportMode, TransportOption } from "../contracts/types";
import { formatDuration, formatUtcDateTime } from "./dates";
import { sumMoney } from "./money";

/** The categories shown to the user, in display order. */
export const TRANSPORT_MODES = [
  "FLIGHT",
  "TRAIN",
  "BUS",
  "ROAD",
] as const satisfies readonly TransportMode[];

export const MODE_LABEL: Record<TransportMode, string> = {
  FLIGHT: "Flight",
  TRAIN: "Train",
  BUS: "Bus",
  ROAD: "Private taxi",
};

export const MODE_PLURAL: Record<TransportMode, string> = {
  FLIGHT: "Flights",
  TRAIN: "Trains",
  BUS: "Buses",
  ROAD: "Private taxis",
};

/** How many vehicles of one type seat a party: party size over seats, rounded up. */
export function vehiclesNeeded(travellers: number, seats: number): number {
  return Math.ceil(travellers / seats);
}

/** The seats of a private taxi, or null for any other option. */
export function seatsOf(option: TransportOption): number | null {
  return option.details?.kind === "ROAD" ? option.details.passenger_capacity : null;
}

export type TransportSortKey = "price" | "duration";

export function durationMinutes(option: TransportOption): number {
  return Math.round((Date.parse(option.arrives_at) - Date.parse(option.departs_at)) / 60_000);
}

/** Ascending. A missing price sorts last, never as zero. Ties keep a stable order by id. */
export function sortTransport(
  options: readonly TransportOption[],
  key: TransportSortKey,
): TransportOption[] {
  const rank = (option: TransportOption): [number, number] => {
    if (key === "duration") {
      return [0, durationMinutes(option)];
    }
    return option.price === null ? [1, 0] : [0, option.price.amount_minor];
  };
  return [...options].sort((a, b) => {
    const [aMissing, aValue] = rank(a);
    const [bMissing, bValue] = rank(b);
    return aMissing - bMissing || aValue - bValue || a.id.localeCompare(b.id);
  });
}

/** Options split by mode. A mode with no options is not in the result. */
export function groupByMode(
  options: readonly TransportOption[],
): { mode: TransportMode; options: TransportOption[] }[] {
  return TRANSPORT_MODES.map((mode) => ({
    mode,
    options: options.filter((option) => option.mode === mode),
  })).filter((group) => group.options.length > 0);
}

export interface Fact {
  label: string;
  value: string;
}

const NOT_SUPPLIED = "Not supplied";

/** The one fact that belongs to this mode only, or null for a mode that has none. */
export function modeSpecificFact(option: TransportOption): { label: string; value: string | null } | null {
  const details = option.details;
  switch (option.mode) {
    case "FLIGHT":
      return { label: "Cabin class", value: details?.kind === "FLIGHT" ? details.cabin_class : null };
    case "TRAIN":
      return { label: "Class", value: details?.kind === "TRAIN" ? details.travel_class : null };
    case "BUS":
      return { label: "Seat type", value: details?.kind === "BUS" ? details.seat_type : null };
    case "ROAD":
      return { label: "Vehicle", value: details?.kind === "ROAD" ? details.vehicle_type : null };
  }
}

/** Rows for an option card. Only facts that fit the mode appear. */
export function transportFacts(option: TransportOption): Fact[] {
  const facts: Fact[] = [
    { label: "Operator", value: option.operator_name ?? NOT_SUPPLIED },
    { label: "Service", value: option.service_label ?? NOT_SUPPLIED },
    { label: "Departs", value: formatUtcDateTime(option.departs_at) },
    { label: "Arrives", value: formatUtcDateTime(option.arrives_at) },
    { label: "Duration", value: formatDuration(option.departs_at, option.arrives_at) },
  ];
  // A bus or a taxi without a stop count is not asked about stops; a flight or train always is.
  if ((option.mode !== "BUS" && option.mode !== "ROAD") || option.stops !== null) {
    facts.push({ label: "Stops", value: option.stops === null ? NOT_SUPPLIED : String(option.stops) });
  }
  const specific = modeSpecificFact(option);
  if (specific !== null) {
    facts.push({ label: specific.label, value: specific.value ?? NOT_SUPPLIED });
  }
  const seats = seatsOf(option);
  if (seats !== null) {
    facts.push({ label: "Seats", value: String(seats) });
    facts.push({ label: "Price covers", value: "One vehicle, not each traveller" });
  }
  facts.push({ label: "Cancellation", value: option.cancellation_terms ?? NOT_SUPPLIED });
  return facts;
}

/**
 * The quoted price plus the quote's fees, in minor units. Null when the option has no price or
 * the currencies differ: it is never guessed. It is not the full trip estimate.
 */
export function quotedTotal(option: TransportOption, quote: Quote | undefined): Money | null {
  if (option.price === null) {
    return null;
  }
  const fees = quote?.fees ?? [];
  if (fees.some((fee) => fee.amount.currency !== option.price?.currency)) {
    return null;
  }
  return sumMoney([option.price, ...fees.map((fee) => fee.amount)], option.price.currency);
}
