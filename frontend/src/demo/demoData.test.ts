import { describe, expect, test } from "vitest";

import type { TripRequest } from "../contracts/types";
import { EXAMPLE_FORM, validateTripForm, type TripFormValues } from "../lib/tripRequest";
import {
  buildDemoCostEstimate,
  buildDemoItinerary,
  buildDemoOptions,
  estimateTotal,
  PROTOTYPE_MAX_ITINERARY_DAYS,
  stayNights,
} from "./demoData";

function requestFor(overrides: Partial<TripFormValues> = {}): TripRequest {
  const result = validateTripForm({ ...EXAMPLE_FORM, ...overrides });
  if (!result.ok) {
    throw new Error(`Invalid test form: ${JSON.stringify(result.errors)}`);
  }
  return result.request;
}

const roundTrip = requestFor(); // 2026-12-01 to 2026-12-05: four nights
const oneWay = requestFor({ tripKind: "ONE_WAY" });
const sameDay = requestFor({ tripKind: "SAME_DAY_RETURN" });

describe("the demo options are honestly labelled", () => {
  const demo = buildDemoOptions(roundTrip);
  const everyOption = [...demo.transport, ...demo.hotels];

  test("every quote says what its price covers: transport per traveller, hotels per room night", () => {
    for (const option of demo.transport) {
      const quote = demo.quotes[option.id];
      if (quote !== undefined) {
        expect(quote.price_basis).toBe("PER_TRAVELLER");
      }
    }
    for (const hotel of demo.hotels) {
      expect(demo.quotes[hotel.id]?.price_basis).toBe("PER_ROOM_NIGHT");
    }
  });

  test("every option and quote is marked MOCK, never LIVE", () => {
    for (const option of everyOption) {
      expect(option.source.provenance).toBe("MOCK");
    }
    for (const quote of Object.values(demo.quotes)) {
      expect(quote.source.provenance).toBe("MOCK");
    }
  });

  test("the source says it is a fixture, not a provider", () => {
    expect(everyOption[0]?.source.provider_name).toBe("frontend-demo-fixture");
  });

  test("option ids are unique", () => {
    const ids = everyOption.map((option) => option.id);

    expect(new Set(ids).size).toBe(ids.length);
  });

  test("availability is mixed so every label can be seen", () => {
    const labels = new Set(everyOption.map((option) => option.availability));

    expect(labels).toEqual(new Set(["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]));
  });

  test("transport times follow the requested departure date", () => {
    for (const option of demo.transport) {
      expect(option.departs_at.startsWith("2026-12-01T")).toBe(true);
      expect(Date.parse(option.arrives_at)).toBeGreaterThan(Date.parse(option.departs_at));
    }
  });

  test("a fact the demo does not supply stays missing instead of becoming zero", () => {
    const bus = demo.transport.find((option) => option.id === "demo-bus-1");

    expect(bus?.stops).toBeNull();
    expect(bus?.cancellation_terms).toBeNull();
  });

  test("all amounts are whole minor units in one currency", () => {
    const amounts = [
      ...demo.transport.map((option) => option.price),
      ...demo.hotels.map((option) => option.nightly_rate),
      ...Object.values(demo.quotes).flatMap((quote) => [quote.price, ...quote.fees.map((f) => f.amount)]),
    ];

    for (const money of amounts) {
      expect(money).not.toBeNull();
      expect(Number.isSafeInteger(money?.amount_minor)).toBe(true);
      expect(money?.currency).toBe("INR");
    }
  });

  test("quotes match the quote contract and point at real options", () => {
    const ids = new Set(everyOption.map((option) => option.id));

    for (const quote of Object.values(demo.quotes)) {
      expect(ids.has(quote.option_id)).toBe(true);
      expect(quote.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
      expect(Date.parse(quote.valid_until)).toBeGreaterThan(Date.parse(quote.source.retrieved_at));
      for (const fee of quote.fees) {
        expect(fee.amount.currency).toBe(quote.price.currency);
      }
    }
  });

  test("an unavailable option has no quote to approve", () => {
    expect(demo.quotes["demo-flight-1"]).toBeUndefined();
  });
});

describe("stayNights", () => {
  test("is the number of nights for a round trip and zero otherwise", () => {
    expect(stayNights(roundTrip)).toBe(4);
    expect(stayNights(sameDay)).toBe(0);
    expect(stayNights(oneWay)).toBe(0);
  });
});

describe("the demo cost estimate", () => {
  const demo = buildDemoOptions(roundTrip);
  const train = demo.transport[0] ?? null;
  const resort = demo.hotels[0] ?? null;

  test("with nothing selected it has no lines and says what is missing", () => {
    const estimate = buildDemoCostEstimate(roundTrip, null, null, demo.quotes);

    expect(estimate.lines).toEqual([]);
    expect(estimate.missing_items.join(" ")).toMatch(/no option selected/);
    expect(estimate.missing_items.join(" ")).toMatch(/no hotel selected/);
    expect(estimateTotal(estimate).amount_minor).toBe(0);
  });

  test("the total is the exact sum of the lines, in whole minor units", () => {
    const estimate = buildDemoCostEstimate(roundTrip, train, resort, demo.quotes);

    // 2 travellers x 1,500 fare, 4 nights x 6,000 x 1 room, 50 and 100 in fees, then 10% of the
    // transport and accommodation (2,700 rounded up) as contingency; all in paise.
    const transport = 2 * 150_000;
    const hotel = 4 * 600_000;
    const contingency = (transport + hotel) / 10;
    expect(estimateTotal(estimate).amount_minor).toBe(transport + hotel + 5_000 + 10_000 + contingency);
    expect(estimateTotal(estimate).amount_minor).toBe(
      estimate.lines.reduce((sum, line) => sum + line.amount.amount_minor, 0),
    );
  });

  test("every line is MOCK and the estimate lists what it still cannot include", () => {
    const estimate = buildDemoCostEstimate(roundTrip, train, resort, demo.quotes);

    expect(estimate.lines.every((line) => line.provenance === "MOCK")).toBe(true);
    const missing = estimate.missing_items.join(" ");
    expect(missing).toMatch(/return leg is not modelled/);
    expect(missing).toMatch(/Rooms: .* not decided yet/);
  });

  test("the local transport allowance does not apply and is not reported as missing", () => {
    const estimate = buildDemoCostEstimate(roundTrip, train, resort, demo.quotes);

    expect(estimate.lines.some((line) => line.kind === "LOCAL_TRANSPORT")).toBe(false);
    expect(estimate.missing_items.join(" ")).not.toMatch(/Local transport/);
    expect(estimate.lines.find((line) => line.kind === "CONTINGENCY")?.description).toMatch(
      /no local transport allowance yet/,
    );
  });

  test("contingency is 10% of transport and accommodation, not of fees", () => {
    const estimate = buildDemoCostEstimate(roundTrip, train, resort, demo.quotes);
    const amount = (kind: string) =>
      estimate.lines.filter((line) => line.kind === kind).reduce((sum, line) => sum + line.amount.amount_minor, 0);

    expect(amount("CONTINGENCY")).toBe((amount("TRANSPORT") + amount("ACCOMMODATION")) / 10);
  });

  test("a one-way or same-day trip has no accommodation line, and nothing is missing for it", () => {
    for (const request of [oneWay, sameDay]) {
      const options = buildDemoOptions(request);
      const estimate = buildDemoCostEstimate(
        request,
        options.transport[0] ?? null,
        options.hotels[0] ?? null,
        options.quotes,
      );

      expect(estimate.lines.some((line) => line.kind === "ACCOMMODATION")).toBe(false);
      expect(estimate.missing_items.join(" ")).not.toMatch(/Accommodation|stay length|Rooms/);
      // The hotel's fee is not charged either, because there is no stay.
      expect(estimate.lines.some((line) => /resort tax|city tax/i.test(line.description))).toBe(false);
      expect(estimate.lines.some((line) => line.kind === "CONTINGENCY")).toBe(true);
    }
  });

  test("an estimate with no lines always lists missing items, as the backend requires", () => {
    const estimate = buildDemoCostEstimate(oneWay, null, null, demo.quotes);

    expect(estimate.lines).toHaveLength(0);
    expect(estimate.missing_items.length).toBeGreaterThan(0);
  });

  test("the transport fare is scaled by the travellers and the hotel is not", () => {
    const line = (request: TripRequest, kind: string) => {
      const options = buildDemoOptions(request);
      const estimate = buildDemoCostEstimate(
        request,
        options.transport[0] ?? null,
        options.hotels[0] ?? null,
        options.quotes,
      );
      return estimate.lines.find((l) => l.kind === kind)?.amount.amount_minor ?? 0;
    };
    const one = requestFor({ travellers: "1" });
    const five = requestFor({ travellers: "5" });

    expect(line(five, "TRANSPORT")).toBe(5 * line(one, "TRANSPORT"));
    expect(line(five, "ACCOMMODATION")).toBe(line(one, "ACCOMMODATION"));
  });
});

describe("the sample itinerary", () => {
  const demo = buildDemoOptions(roundTrip);
  const train = demo.transport[0] ?? null;
  const resort = demo.hotels[0] ?? null;

  test("a four-night round trip has five numbered days", () => {
    const itinerary = buildDemoItinerary(roundTrip, train, resort);

    expect(itinerary.days.map((day) => day.day_number)).toEqual([1, 2, 3, 4, 5]);
  });

  test("it points at the selected options by id", () => {
    const itinerary = buildDemoItinerary(roundTrip, train, resort);
    const linked = itinerary.days.flatMap((day) => day.items.map((item) => item.option_id));

    expect(linked).toContain("demo-train-1");
    expect(linked).toContain("demo-hotel-1");
  });

  test("it makes no option links when nothing is selected", () => {
    const itinerary = buildDemoItinerary(roundTrip, null, null);

    expect(itinerary.days.flatMap((day) => day.items).every((item) => item.option_id === null)).toBe(true);
  });

  test("one-way is a single day with no return journey", () => {
    const titles = buildDemoItinerary(oneWay, train, resort).days.flatMap((day) =>
      day.items.map((item) => item.title),
    );

    expect(buildDemoItinerary(oneWay, train, resort).days).toHaveLength(1);
    expect(titles).not.toContain("Return journey");
  });

  test("a same-day return is a single day that ends with the return journey", () => {
    const itinerary = buildDemoItinerary(sameDay, train, resort);
    const titles = itinerary.days[0]?.items.map((item) => item.title) ?? [];

    expect(itinerary.days).toHaveLength(1);
    expect(titles.at(-1)).toBe("Return journey");
    expect(titles).not.toContain("Check in");
  });

  test("a very long trip is cut short and says so", () => {
    const long = requestFor({ returnDate: "2027-03-01" });
    const itinerary = buildDemoItinerary(long, null, null);

    expect(itinerary.days).toHaveLength(PROTOTYPE_MAX_ITINERARY_DAYS);
    expect(itinerary.notes).toMatch(/first 14 of/);
  });

  test("it never states a price, a currency or a time, and says it is not AI-written", () => {
    const itinerary = buildDemoItinerary(roundTrip, train, resort);
    const text = [
      itinerary.notes ?? "",
      ...itinerary.days.flatMap((day) =>
        day.items.flatMap((item) => [item.title, item.description ?? ""]),
      ),
    ].join(" ");

    expect(text).not.toMatch(/[₹$€£]|\bRs\b|\bINR\b|\d{1,2}:\d{2}/);
    expect(itinerary.notes).toMatch(/not by an AI model/);
  });
});
