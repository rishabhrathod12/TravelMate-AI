/**
 * DEMO DATA. Nothing in this file comes from a provider.
 *
 * Every value is fictional, typed to the backend contract and labelled MOCK. Hotels,
 * quotes and fees are hand-written here. The flight, train and bus services are templates
 * generated from the backend mock fixtures (`transportFixtures.json`), so there is one
 * source of truth. Names are fictional and amounts are round placeholders. They must never
 * be shown as real prices, schedules or availability. Nothing here calls a backend: only
 * `GET /health` exists today.
 *
 * Prices follow the owner's rules (PRD Q12, Q13, Q18): a transport fare is per traveller, a hotel
 * price is per room per night, a one-way or same-day trip has no hotel stay, and contingency is
 * 10% of transport and accommodation, rounded up. How many rooms a party needs is still open, so
 * the estimate uses one room and says so.
 */

import type {
  CostEstimate,
  CostLine,
  HotelOption,
  Itinerary,
  ItineraryDay,
  Money,
  PriceBasis,
  Quote,
  SourceMetadata,
  TransportOption,
  TripRequest,
} from "../contracts/types";
import { addDays, daysBetween } from "../lib/dates";
import { multiplyMoney, percentageRoundedUp, sumMoney } from "../lib/money";
import transportFixtures from "./transportFixtures.json";

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

/**
 * One fictional service template, exported from the backend mock fixtures
 * (`backend/app/providers/mock/fixtures.py`). The file is generated; a backend test fails if it
 * is out of date, so the two sides cannot drift apart.
 */
interface TransportTemplate {
  key: string;
  mode: Exclude<TransportOption["mode"], "ROAD">;
  operator_name: string;
  service_label: string;
  departs: { hour: number; minute: number };
  arrives: { day_offset: number; hour: number; minute: number };
  stops: number | null;
  price_minor: number;
  currency: string;
  availability: TransportOption["availability"];
  cancellation_terms: string | null;
  detail: string | null;
}

export const TRANSPORT_FIXTURES = transportFixtures as unknown as {
  note: string;
  mock_text_note: string;
  services: TransportTemplate[];
};

/** Sample fees, keyed by mode. They exist only in this prototype; the backend mock has no fees. */
const TRANSPORT_FEES: Record<TransportOption["mode"], { label: string; amount_minor: number }> = {
  FLIGHT: { label: "Sample convenience fee", amount_minor: 15_000 },
  TRAIN: { label: "Sample booking fee", amount_minor: 5_000 },
  BUS: { label: "Sample booking fee", amount_minor: 2_000 },
  ROAD: { label: "Sample fee", amount_minor: 0 },
};

function isoAt(day: string, dayOffset: number, hour: number, minute: number): string {
  return `${addDays(day, dayOffset)}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00Z`;
}

function detailsFor(template: TransportTemplate): TransportOption["details"] {
  if (template.detail === null) {
    return null;
  }
  switch (template.mode) {
    case "FLIGHT":
      return { kind: "FLIGHT", cabin_class: template.detail };
    case "TRAIN":
      return { kind: "TRAIN", travel_class: template.detail };
    case "BUS":
      return { kind: "BUS", seat_type: template.detail };
  }
}

function transportFromTemplate(
  template: TransportTemplate,
  day: string,
  route: Pick<TransportOption, "origin" | "destination">,
): TransportOption {
  return {
    id: `demo-${template.key}`,
    source: DEMO_SOURCE,
    availability: template.availability,
    cancellation_terms: template.cancellation_terms,
    mode: template.mode,
    ...route,
    departs_at: isoAt(day, 0, template.departs.hour, template.departs.minute),
    arrives_at: isoAt(day, template.arrives.day_offset, template.arrives.hour, template.arrives.minute),
    stops: template.stops,
    price: { amount_minor: template.price_minor, currency: template.currency },
    operator_name: template.operator_name,
    service_label: template.service_label,
    details: detailsFor(template),
  };
}

function demoQuote(
  suffix: string,
  option: { id: string; availability: Quote["availability"]; cancellation_terms: string | null },
  price: Money,
  priceBasis: PriceBasis,
  feeAmount: number,
  feeLabel: string,
): Quote {
  return {
    id: `00000000-0000-4000-8000-${suffix.padStart(12, "0")}`,
    option_id: option.id,
    price,
    price_basis: priceBasis,
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

  const transport = TRANSPORT_FIXTURES.services.map((service) =>
    transportFromTemplate(service, day, route),
  );

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
    [resort.id]: demoQuote("b1", resort, inr(600_000), "PER_ROOM_NIGHT", 10_000, "Sample resort tax"),
    [inn.id]: demoQuote("b2", inn, inr(300_000), "PER_ROOM_NIGHT", 5_000, "Sample city tax"),
  };
  // An unavailable option has nothing to quote.
  transport.forEach((option, index) => {
    if (option.price !== null && option.availability !== "UNAVAILABLE") {
      const fee = TRANSPORT_FEES[option.mode];
      quotes[option.id] = demoQuote(
        `a${String(index + 1).padStart(2, "0")}`,
        option,
        option.price,
        "PER_TRAVELLER",
        fee.amount_minor,
        fee.label,
      );
    }
  });

  return { transport, hotels: [resort, inn], quotes };
}

/** Nights between departure and return; 0 for one-way and same-day trips. */
export function stayNights(request: TripRequest): number {
  if (request.trip_type !== "ROUND_TRIP" || request.return_date === null) {
    return 0;
  }
  return Math.max(0, daysBetween(request.departure_date, request.return_date));
}

/** The owner's contingency (Q18): 10% of transport and accommodation, rounded up. */
export const CONTINGENCY_BASIS_POINTS = 1000;

/** Rooms are not decided yet (PRD Q14), so the demo uses one room and says so. */
const DEMO_ROOMS = 1;

/**
 * A demo estimate that follows the owner's rules (Q12, Q13, Q18). It is not the backend estimator
 * but it applies the same ones: the transport fare is multiplied by the travellers, the hotel
 * price by nights and rooms, a one-way or same-day trip has no accommodation line (nothing is
 * missing, there is no stay), fees are added as quoted, and contingency is 10% of transport and
 * accommodation rounded up. The local transport allowance does not apply until the owner sets an
 * amount. What it cannot include is always listed, so a total is never silently incomplete.
 */
export function buildDemoCostEstimate(
  request: TripRequest,
  transport: TransportOption | null,
  hotel: HotelOption | null,
  quotes: Record<string, Quote>,
): CostEstimate {
  const lines: CostLine[] = [];
  const missing: string[] = [];
  const travellers = request.travellers.length;
  const travellerWord = travellers === 1 ? "traveller" : "travellers";

  if (transport === null) {
    missing.push("Transport: no option selected");
  } else if (transport.price === null) {
    missing.push("Transport: the option has no price");
  } else {
    lines.push({
      kind: "TRANSPORT",
      description: `Transport: ${travellers} ${travellerWord} at the quoted fare`,
      amount: multiplyMoney(transport.price, travellers),
      provenance: "MOCK",
    });
    if (request.trip_type === "ROUND_TRIP") {
      missing.push("Transport: the return leg is not modelled in this prototype (1 of 2 legs priced)");
    }
  }

  const nights = stayNights(request);
  if (nights >= 1) {
    if (hotel === null) {
      missing.push("Accommodation: no hotel selected");
    } else if (hotel.nightly_rate === null) {
      missing.push("Accommodation: the hotel has no room rate");
    } else {
      lines.push({
        kind: "ACCOMMODATION",
        description: `${hotel.name}: ${nights} night${nights === 1 ? "" : "s"}, ${DEMO_ROOMS} room at the quoted room rate`,
        amount: multiplyMoney(hotel.nightly_rate, nights * DEMO_ROOMS),
        provenance: "MOCK",
      });
      missing.push("Rooms: how many rooms a party needs is not decided yet, so 1 room is used");
    }
  }

  for (const option of [transport, hotel]) {
    const quote = option === null ? undefined : quotes[option.id];
    if (option === hotel && nights < 1) {
      continue;
    }
    for (const fee of quote?.fees ?? []) {
      lines.push({
        kind: "TAXES_AND_FEES",
        description: `${fee.label} (as quoted)`,
        amount: fee.amount,
        provenance: "MOCK",
      });
    }
  }

  const base = lines.filter((line) => line.kind === "TRANSPORT" || line.kind === "ACCOMMODATION");
  if (base.length === 0) {
    missing.push("Contingency: there are no priced lines to apply it to");
  } else {
    lines.push({
      kind: "CONTINGENCY",
      description:
        "Contingency at 10.00% of transport and accommodation, rounded up (no local transport allowance yet)",
      amount: percentageRoundedUp(
        sumMoney(
          base.map((line) => line.amount),
          CURRENCY,
        ),
        CONTINGENCY_BASIS_POINTS,
      ),
      provenance: "MOCK",
    });
  }

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
