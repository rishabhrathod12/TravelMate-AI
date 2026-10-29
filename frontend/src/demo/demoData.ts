/**
 * DEMO DATA. Nothing in this file comes from a provider.
 *
 * Every value is hand-written, typed to the backend contract and labelled MOCK.
 * Names are fictional and amounts are round placeholders. They must never be
 * shown as real prices, schedules or availability. The real mock providers
 * arrive with Milestone 3 on the backend; this file only lets the screens be
 * viewed before then.
 *
 * Prices are not scaled by traveller count or room count: what a quoted price
 * covers is an open decision (PRD Q12).
 */

import type {
  CostEstimate,
  CostLine,
  HotelOption,
  Itinerary,
  ItineraryDay,
  Money,
  Quote,
  SourceMetadata,
  TransportOption,
  TripRequest,
} from "../contracts/types";
import { daysBetween } from "../lib/dates";
import { multiplyMoney, sumMoney } from "../lib/money";

export const DEMO_NOTICE =
  "Demo data: sample values written by hand. They are not real prices, availability, schedules or weather, and nothing is booked.";

/** Prototype-only: keeps the sample itinerary short for very long trips. */
export const PROTOTYPE_MAX_ITINERARY_DAYS = 14;

const CURRENCY = "INR";

function inr(amountMinor: number): Money {
  return { amount_minor: amountMinor, currency: CURRENCY };
}

/** A fixed, fictional timestamp. It is not a real retrieval time. */
const DEMO_SOURCE: SourceMetadata = {
  provenance: "MOCK",
  provider_name: "frontend-demo-fixture",
  retrieved_at: "2026-11-01T09:00:00Z",
  freshness_window_seconds: 900,
};

const DEMO_VALID_UNTIL = "2026-11-01T09:15:00Z";

export interface DemoOptions {
  transport: TransportOption[];
  hotels: HotelOption[];
  quotes: Record<string, Quote>;
}

function demoQuote(
  suffix: string,
  option: { id: string; availability: Quote["availability"]; cancellation_terms: string | null },
  price: Money,
  feeAmount: number,
  feeLabel: string,
): Quote {
  return {
    id: `00000000-0000-4000-8000-0000000000${suffix}`,
    option_id: option.id,
    price,
    fees: [{ label: feeLabel, amount: inr(feeAmount) }],
    availability: option.availability,
    cancellation_terms: option.cancellation_terms,
    valid_until: DEMO_VALID_UNTIL,
    source: DEMO_SOURCE,
  };
}

export function buildDemoOptions(request: TripRequest): DemoOptions {
  const day = request.departure_date;
  const route = { origin: request.origin, destination: request.destination };

  const train: TransportOption = {
    id: "demo-train-1",
    source: DEMO_SOURCE,
    availability: "AVAILABLE",
    cancellation_terms: "Demo text: cancellation terms would come from the provider.",
    mode: "TRAIN",
    ...route,
    departs_at: `${day}T04:00:00Z`,
    arrives_at: `${day}T16:30:00Z`,
    stops: 1,
    price: inr(150_000),
  };
  const bus: TransportOption = {
    id: "demo-bus-1",
    source: DEMO_SOURCE,
    availability: "UNKNOWN",
    cancellation_terms: null,
    mode: "BUS",
    ...route,
    departs_at: `${day}T02:00:00Z`,
    arrives_at: `${day}T17:00:00Z`,
    stops: null,
    price: inr(120_000),
  };
  const flight: TransportOption = {
    id: "demo-flight-1",
    source: DEMO_SOURCE,
    availability: "UNAVAILABLE",
    cancellation_terms: null,
    mode: "FLIGHT",
    ...route,
    departs_at: `${day}T08:00:00Z`,
    arrives_at: `${day}T09:45:00Z`,
    stops: 0,
    price: inr(500_000),
  };

  const resort: HotelOption = {
    id: "demo-hotel-1",
    source: DEMO_SOURCE,
    availability: "AVAILABLE",
    cancellation_terms: "Demo text: cancellation terms would come from the provider.",
    name: "Sample Beach Resort",
    location: request.destination,
    nightly_rate: inr(600_000),
  };
  const inn: HotelOption = {
    id: "demo-hotel-2",
    source: DEMO_SOURCE,
    availability: "UNKNOWN",
    cancellation_terms: null,
    name: "Demo City Inn",
    location: request.destination,
    nightly_rate: inr(300_000),
  };

  const quotes: Record<string, Quote> = {
    [train.id]: demoQuote("a1", train, inr(150_000), 5_000, "Sample booking fee"),
    [bus.id]: demoQuote("a2", bus, inr(120_000), 2_000, "Sample booking fee"),
    [resort.id]: demoQuote("b1", resort, inr(600_000), 10_000, "Sample resort tax"),
    [inn.id]: demoQuote("b2", inn, inr(300_000), 5_000, "Sample city tax"),
  };

  return { transport: [train, bus, flight], hotels: [resort, inn], quotes };
}

/** Nights between departure and return; 0 for one-way and same-day trips. */
export function stayNights(request: TripRequest): number {
  if (request.trip_type !== "ROUND_TRIP" || request.return_date === null) {
    return 0;
  }
  return Math.max(0, daysBetween(request.departure_date, request.return_date));
}

/**
 * A demo estimate. It is not the Milestone 5 estimator: it only adds up the
 * lines it has and always lists what it cannot include, so a total is never
 * silently incomplete.
 */
export function buildDemoCostEstimate(
  request: TripRequest,
  transport: TransportOption | null,
  hotel: HotelOption | null,
  quotes: Record<string, Quote>,
): CostEstimate {
  const lines: CostLine[] = [];
  const missing: string[] = [];

  if (transport === null) {
    missing.push("Transport: no option selected");
  } else if (transport.price === null) {
    missing.push("Transport: the option has no price");
  } else {
    lines.push({
      kind: "TRANSPORT",
      description:
        request.trip_type === "ROUND_TRIP"
          ? "Transport, price as quoted (return leg not modelled in this prototype)"
          : "Transport, price as quoted",
      amount: transport.price,
      provenance: "MOCK",
    });
  }

  const nights = stayNights(request);
  if (hotel === null) {
    missing.push("Accommodation: no hotel selected");
  } else if (hotel.nightly_rate === null) {
    missing.push("Accommodation: the hotel has no nightly rate");
  } else if (nights < 1) {
    missing.push(
      "Accommodation: the stay length is not defined for one-way and same-day trips (open question Q13)",
    );
  } else {
    lines.push({
      kind: "ACCOMMODATION",
      description: `${hotel.name}: ${nights} night${nights === 1 ? "" : "s"} at the quoted nightly rate (room count not defined)`,
      amount: multiplyMoney(hotel.nightly_rate, nights),
      provenance: "MOCK",
    });
  }

  for (const option of [transport, hotel]) {
    const quote = option === null ? undefined : quotes[option.id];
    for (const fee of quote?.fees ?? []) {
      lines.push({
        kind: "TAXES_AND_FEES",
        description: fee.label,
        amount: fee.amount,
        provenance: "MOCK",
      });
    }
  }

  missing.push("Local transport allowance: rules not defined yet");
  missing.push("Contingency: percentage and rounding rules not decided yet");

  return { currency: CURRENCY, lines, missing_items: missing };
}

export function estimateTotal(estimate: CostEstimate): Money {
  return sumMoney(
    estimate.lines.map((line) => line.amount),
    estimate.currency,
  );
}

/**
 * A sample itinerary, written by hand from a fixed template. It is not produced
 * by an AI model. Days are numbered; calendar dates are worked out by the screen
 * from the departure date. Activity text is deliberately generic.
 */
export function buildDemoItinerary(
  request: TripRequest,
  transport: TransportOption | null,
  hotel: HotelOption | null,
): Itinerary {
  const nights = stayNights(request);
  const totalDays = request.trip_type === "ROUND_TRIP" ? nights + 1 : 1;
  const shownDays = Math.min(totalDays, PROTOTYPE_MAX_ITINERARY_DAYS);
  const destination = request.destination.name;
  const stays = nights >= 1;

  const days: ItineraryDay[] = [];
  for (let number = 1; number <= shownDays; number += 1) {
    const items: ItineraryDay["items"] = [];
    const isFirst = number === 1;
    const isLast = number === totalDays;

    if (isFirst) {
      items.push({
        title: `Travel to ${destination}`,
        description: "Sample entry for the selected transport option.",
        option_id: transport?.id ?? null,
      });
      if (stays) {
        items.push({
          title: "Check in",
          description: "Sample entry for the selected hotel.",
          option_id: hotel?.id ?? null,
        });
      }
      items.push({
        title: isLast ? `Time in ${destination} (sample)` : "Settle in (sample)",
        description: null,
        option_id: null,
      });
    } else {
      items.push({ title: "Morning at leisure (sample)", description: null, option_id: null });
      items.push({ title: "Local sightseeing (sample)", description: null, option_id: null });
      items.push({ title: "Free afternoon (sample)", description: null, option_id: null });
    }

    if (isLast && request.trip_type === "ROUND_TRIP") {
      if (stays) {
        items.push({
          title: "Check out",
          description: "Sample entry for the selected hotel.",
          option_id: hotel?.id ?? null,
        });
      }
      items.push({
        title: "Return journey",
        description: "Return-leg options are not modelled in this prototype.",
        option_id: null,
      });
    }

    days.push({ day_number: number, items });
  }

  const notes =
    totalDays > shownDays
      ? `Sample itinerary written by hand, not by an AI model. This prototype shows the first ${shownDays} of ${totalDays} days.`
      : "Sample itinerary written by hand, not by an AI model.";
  return { days, notes };
}
