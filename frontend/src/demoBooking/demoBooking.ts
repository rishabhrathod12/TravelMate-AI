/**
 * Simulated booking, for demonstration only (ADR 0003).
 *
 * This module is deliberately separate from the real booking lifecycle. It never uses
 * `BookingIntent`, `Approval` or a `CONFIRMED` status, never reads `BOOKING_ENABLED`, and
 * never talks to anything: it has no network access, no provider and no payment. A result
 * here is not a booking and not a provider confirmation. It is pure code with no I/O, so it
 * cannot reserve, ticket or charge anything.
 */

import type { Fee, Money, Quote, SourceMetadata, TransportMode, TransportOption, TripRequest } from "../contracts/types";
import { sumMoney } from "../lib/money";

export const DEMO_BOOKING_LABEL = "DEMO — NOT A REAL BOOKING";

/** Shown with every demo booking, before and after. */
export const DEMO_DISCLAIMERS: readonly string[] = [
  "No actual transport is reserved.",
  "No real ticket is issued.",
  "No payment is collected.",
  "Availability and prices are fictional demo data.",
  "A simulated confirmation is not a real provider confirmation.",
];

const DEMO_BOOKABLE_MODES: readonly TransportMode[] = ["FLIGHT", "TRAIN", "BUS"];

export type Eligibility = { ok: true } | { ok: false; reason: string };

/**
 * Only an option that is shown as available, has a price and has a matching quote can be
 * simulated. Unknown availability is not enough: the simulation does not guess (decision D).
 */
export function checkEligibility(
  option: TransportOption | null,
  quote: Quote | undefined,
): Eligibility {
  if (option === null) {
    return { ok: false, reason: "Select a flight, train or bus to try a demo booking." };
  }
  if (!DEMO_BOOKABLE_MODES.includes(option.mode)) {
    return { ok: false, reason: "Demo booking is available for flights, trains and buses only." };
  }
  if (option.availability === "UNAVAILABLE") {
    return { ok: false, reason: "This option is shown as unavailable, so it cannot be simulated." };
  }
  if (option.availability === "UNKNOWN") {
    return {
      ok: false,
      reason: "Availability is unknown for this option, so a demo booking cannot be simulated.",
    };
  }
  if (option.price === null) {
    return { ok: false, reason: "This option has no price, so a demo booking cannot be simulated." };
  }
  if (quote === undefined || quote.option_id !== option.id) {
    return { ok: false, reason: "There is no demo quote for this option." };
  }
  if (
    quote.price.currency !== option.price.currency ||
    quote.fees.some((fee) => fee.amount.currency !== option.price?.currency)
  ) {
    return { ok: false, reason: "The quote and the option use different currencies." };
  }
  return { ok: true };
}

/** What the simulation produced. `is_real` is always false and there is no provider reference. */
export interface DemoBooking {
  readonly kind: "DEMO_SIMULATION";
  readonly is_real: false;
  /** A sample number for this browser session. It is not a PNR, a ticket number or a booking ID. */
  readonly reference: string;
  readonly option_id: string;
  readonly mode: TransportMode;
  readonly operator_name: string | null;
  readonly service_label: string | null;
  readonly origin: string;
  readonly destination: string;
  readonly departs_at: string;
  readonly arrives_at: string;
  readonly price: Money;
  readonly fees: readonly Fee[];
  /** Quoted price plus sample fees, as quoted. Not the trip estimate. */
  readonly quoted_total: Money;
  readonly source: SourceMetadata;
}

export function formatDemoReference(sequence: number): string {
  return `DEMO-BOOKING-${String(sequence).padStart(3, "0")}`;
}

export class DemoBookingNotAllowedError extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = "DemoBookingNotAllowedError";
  }
}

export interface SubmitResult {
  booking: DemoBooking;
  /** True when this selection had already been simulated: nothing new was created. */
  duplicate: boolean;
}

/**
 * Keeps the simulated bookings of one browser session in memory. Submitting the same selection
 * again returns the first result instead of creating another (an idempotency key made from the
 * option and the trip). Nothing is stored anywhere else, so a reload starts again at 001.
 */
export class DemoBookingRegistry {
  private readonly bookings = new Map<string, DemoBooking>();
  private next = 1;

  static keyFor(optionId: string, request: TripRequest): string {
    return [
      optionId,
      request.origin.name,
      request.destination.name,
      request.departure_date,
      request.travellers.length,
    ].join("|");
  }

  find(optionId: string, request: TripRequest): DemoBooking | undefined {
    return this.bookings.get(DemoBookingRegistry.keyFor(optionId, request));
  }

  all(): DemoBooking[] {
    return [...this.bookings.values()];
  }

  submit(option: TransportOption, quote: Quote | undefined, request: TripRequest): SubmitResult {
    const key = DemoBookingRegistry.keyFor(option.id, request);
    const existing = this.bookings.get(key);
    if (existing !== undefined) {
      return { booking: existing, duplicate: true };
    }

    const eligibility = checkEligibility(option, quote);
    if (!eligibility.ok || option.price === null || quote === undefined) {
      throw new DemoBookingNotAllowedError(
        eligibility.ok ? "This option cannot be simulated." : eligibility.reason,
      );
    }

    const booking: DemoBooking = {
      kind: "DEMO_SIMULATION",
      is_real: false,
      reference: formatDemoReference(this.next),
      option_id: option.id,
      mode: option.mode,
      operator_name: option.operator_name,
      service_label: option.service_label,
      origin: option.origin.name,
      destination: option.destination.name,
      departs_at: option.departs_at,
      arrives_at: option.arrives_at,
      price: option.price,
      fees: quote.fees,
      quoted_total: sumMoney(
        [option.price, ...quote.fees.map((fee) => fee.amount)],
        option.price.currency,
      ),
      source: option.source,
    };
    this.next += 1;
    this.bookings.set(key, booking);
    return { booking, duplicate: false };
  }
}
