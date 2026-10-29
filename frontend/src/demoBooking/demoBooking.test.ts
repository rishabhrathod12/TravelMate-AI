import { afterEach, describe, expect, test, vi } from "vitest";

import type { Quote, TransportOption, TripRequest } from "../contracts/types";
import { buildDemoOptions } from "../demo/demoData";
import { EXAMPLE_FORM, validateTripForm } from "../lib/tripRequest";
import {
  checkEligibility,
  DEMO_BOOKING_LABEL,
  DEMO_DISCLAIMERS,
  DemoBookingNotAllowedError,
  DemoBookingRegistry,
  formatDemoReference,
} from "./demoBooking";

function requestWith(overrides: Partial<typeof EXAMPLE_FORM> = {}): TripRequest {
  const result = validateTripForm({ ...EXAMPLE_FORM, ...overrides });
  if (!result.ok) {
    throw new Error("Invalid test form");
  }
  return result.request;
}

const request = requestWith();
const demo = buildDemoOptions(request);
const option = (label: string): TransportOption => {
  const found = demo.transport.find((candidate) => candidate.service_label === label);
  if (found === undefined) {
    throw new Error(`No demo service ${label}`);
  }
  return found;
};
const quoteOf = (value: TransportOption): Quote | undefined => demo.quotes[value.id];

const train = option("DEMO-T201"); // AVAILABLE, priced, quoted
const bus = option("DEMO-B302"); // AVAILABLE, priced, quoted
const unknownBus = option("DEMO-B301"); // UNKNOWN availability
const soldOutFlight = option("DEMO-F101"); // UNAVAILABLE

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("who can be demo-booked", () => {
  test("an available, priced option with a matching quote can", () => {
    expect(checkEligibility(train, quoteOf(train))).toEqual({ ok: true });
  });

  test("nothing selected, an unavailable option and an unknown-availability option cannot", () => {
    expect(checkEligibility(null, undefined)).toMatchObject({ ok: false });
    expect(checkEligibility(soldOutFlight, quoteOf(soldOutFlight))).toMatchObject({
      ok: false,
      reason: expect.stringContaining("unavailable"),
    });
    expect(checkEligibility(unknownBus, quoteOf(unknownBus))).toMatchObject({
      ok: false,
      reason: expect.stringContaining("unknown"),
    });
  });

  test("an option with no price, no quote, another option's quote or another currency cannot", () => {
    const quote = quoteOf(train);

    expect(checkEligibility({ ...train, price: null }, quote)).toMatchObject({ ok: false });
    expect(checkEligibility(train, undefined)).toMatchObject({ ok: false });
    expect(checkEligibility(train, quoteOf(bus))).toMatchObject({ ok: false });
    expect(
      checkEligibility(train, {
        ...(quote as Quote),
        price: { amount_minor: 1, currency: "USD" },
      }),
    ).toMatchObject({ ok: false, reason: expect.stringContaining("currencies") });
  });

  test("a mode that is not a flight, train or bus cannot", () => {
    expect(checkEligibility({ ...train, mode: "ROAD", details: null }, quoteOf(train))).toMatchObject({
      ok: false,
    });
  });
});

describe("the demo reference", () => {
  test("is a counter that starts at 001 and cannot be mistaken for a real reference", () => {
    expect(formatDemoReference(1)).toBe("DEMO-BOOKING-001");
    expect(formatDemoReference(12)).toBe("DEMO-BOOKING-012");
    for (const value of [1, 2, 999]) {
      const reference = formatDemoReference(value);
      expect(reference).toMatch(/^DEMO-BOOKING-\d{3}$/);
      // Not a six-character airline-style code and not a ten-digit rail-style number.
      expect(reference).not.toMatch(/^[A-Z0-9]{6}$/);
      expect(reference).not.toMatch(/^\d{10}$/);
    }
  });
});

describe("simulating a booking", () => {
  test("creates a result that says it is not real and has no provider reference", () => {
    const registry = new DemoBookingRegistry();

    const { booking, duplicate } = registry.submit(train, quoteOf(train), request);

    expect(duplicate).toBe(false);
    expect(booking.kind).toBe("DEMO_SIMULATION");
    expect(booking.is_real).toBe(false);
    expect(booking.reference).toBe("DEMO-BOOKING-001");
    expect(booking.source.provenance).toBe("MOCK");
    expect(Object.keys(booking)).not.toEqual(
      expect.arrayContaining(["pnr", "ticket_number", "provider_reference", "confirmation"]),
    );
    expect(DEMO_BOOKING_LABEL).toBe("DEMO — NOT A REAL BOOKING");
  });

  test("the total is the quoted price plus the sample fees, in whole minor units", () => {
    const { booking } = new DemoBookingRegistry().submit(train, quoteOf(train), request);

    expect(booking.quoted_total).toEqual({ amount_minor: 150_000 + 5_000, currency: "INR" });
    expect(Number.isSafeInteger(booking.quoted_total.amount_minor)).toBe(true);
  });

  test("submitting the same selection again returns the first result and creates nothing new", () => {
    const registry = new DemoBookingRegistry();
    const first = registry.submit(train, quoteOf(train), request);

    const again = registry.submit(train, quoteOf(train), request);

    expect(again.duplicate).toBe(true);
    expect(again.booking).toBe(first.booking);
    expect(registry.all()).toHaveLength(1);
    // The counter did not move: the next new booking is 002, not 003.
    expect(registry.submit(bus, quoteOf(bus), request).booking.reference).toBe("DEMO-BOOKING-002");
  });

  test("a different option, or the same option for a different trip, is a new simulation", () => {
    const registry = new DemoBookingRegistry();
    registry.submit(train, quoteOf(train), request);

    const otherDay = requestWith({ departureDate: "2026-12-02", returnDate: "2026-12-06" });
    const sameOptionOtherTrip = registry.submit(train, quoteOf(train), otherDay);
    const otherOption = registry.submit(bus, quoteOf(bus), request);

    expect(sameOptionOtherTrip.duplicate).toBe(false);
    expect(otherOption.duplicate).toBe(false);
    expect(registry.all().map((b) => b.reference)).toEqual([
      "DEMO-BOOKING-001",
      "DEMO-BOOKING-002",
      "DEMO-BOOKING-003",
    ]);
  });

  test("an option that cannot be simulated is refused and uses up no reference", () => {
    const registry = new DemoBookingRegistry();

    expect(() => registry.submit(unknownBus, quoteOf(unknownBus), request)).toThrow(
      DemoBookingNotAllowedError,
    );
    expect(() => registry.submit(soldOutFlight, undefined, request)).toThrow(
      DemoBookingNotAllowedError,
    );
    expect(registry.all()).toEqual([]);
    expect(registry.submit(train, quoteOf(train), request).booking.reference).toBe("DEMO-BOOKING-001");
  });

  test("can be found again for the same selection", () => {
    const registry = new DemoBookingRegistry();
    const { booking } = registry.submit(train, quoteOf(train), request);

    expect(registry.find(train.id, request)).toBe(booking);
    expect(registry.find(bus.id, request)).toBeUndefined();
  });

  test("makes no network call and touches no storage", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const storage = vi.fn();
    vi.stubGlobal("localStorage", { getItem: storage, setItem: storage, removeItem: storage });

    new DemoBookingRegistry().submit(train, quoteOf(train), request);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(storage).not.toHaveBeenCalled();
  });
});

describe("the disclaimers", () => {
  test("say every required thing", () => {
    const text = DEMO_DISCLAIMERS.join(" ");

    expect(text).toMatch(/No actual transport is reserved/);
    expect(text).toMatch(/No real ticket is issued/);
    expect(text).toMatch(/No payment is collected/);
    expect(text).toMatch(/fictional demo data/);
    expect(text).toMatch(/not a real provider confirmation/);
  });
});

describe("the demo booking code is separate from real booking and from the network", () => {
  const modules = import.meta.glob(
    ["./*.ts", "!./*.test.ts", "../components/demoBooking/*.tsx"],
    { query: "?raw", import: "default", eager: true },
  ) as Record<string, string>;

  const withoutComments = (source: string) =>
    source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

  test("there are source files to check", () => {
    expect(Object.keys(modules).length).toBeGreaterThanOrEqual(3);
  });

  test.each(Object.entries(modules))("%s has no network, storage or real-booking references", (_path, source) => {
    const code = withoutComments(source);

    for (const forbidden of [
      /\bfetch\s*\(/,
      /XMLHttpRequest/,
      /WebSocket/,
      /EventSource/,
      /sendBeacon/,
      /localStorage|sessionStorage|indexedDB/,
      /\.\.\/api\//,
      /\.\.\/voice\//,
      /BOOKING_ENABLED/,
      /BookingIntent|BookingStatus|\bApproval\b|CONFIRMED/,
    ]) {
      expect(code).not.toMatch(forbidden);
    }
  });
});
