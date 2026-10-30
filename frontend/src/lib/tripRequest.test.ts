import { describe, expect, test } from "vitest";

import {
  EXAMPLE_FORM,
  MAX_TRAVELLERS,
  validateTripForm,
  type TripFormValues,
} from "./tripRequest";

function values(overrides: Partial<TripFormValues> = {}): TripFormValues {
  return { ...EXAMPLE_FORM, ...overrides };
}

function expectOk(form: TripFormValues) {
  const result = validateTripForm(form);
  if (!result.ok) {
    throw new Error(`Expected a valid form, got ${JSON.stringify(result.errors)}`);
  }
  return result.request;
}

function expectErrors(form: TripFormValues) {
  const result = validateTripForm(form);
  if (result.ok) {
    throw new Error("Expected validation errors");
  }
  return result.errors;
}

describe("the three trip kinds", () => {
  test("a round trip keeps both dates", () => {
    const request = expectOk(values());

    expect(request.trip_type).toBe("ROUND_TRIP");
    expect(request.departure_date).toBe("2026-12-01");
    expect(request.return_date).toBe("2026-12-05");
  });

  test("a one-way trip has no return date, even if one was typed earlier", () => {
    const request = expectOk(values({ tripKind: "ONE_WAY", returnDate: "2026-12-05" }));

    expect(request.trip_type).toBe("ONE_WAY");
    expect(request.return_date).toBeNull();
  });

  test("a one-way trip needs no return date", () => {
    expect(expectOk(values({ tripKind: "ONE_WAY", returnDate: "" })).return_date).toBeNull();
  });

  test("a same-day return is a round trip with the same date", () => {
    const request = expectOk(values({ tripKind: "SAME_DAY_RETURN", returnDate: "" }));

    expect(request.trip_type).toBe("ROUND_TRIP");
    expect(request.return_date).toBe(request.departure_date);
  });

  test("a round trip may return on the departure date", () => {
    expect(expectOk(values({ returnDate: "2026-12-01" })).return_date).toBe("2026-12-01");
  });
});

describe("date errors", () => {
  test("a round trip needs a return date", () => {
    expect(expectErrors(values({ returnDate: "" })).returnDate).toMatch(/return date/i);
  });

  test("the return date cannot be before departure", () => {
    expect(expectErrors(values({ returnDate: "2026-11-30" })).returnDate).toMatch(
      /on or after the departure/i,
    );
  });

  test("a departure date is required and must be real", () => {
    expect(expectErrors(values({ departureDate: "" })).departureDate).toMatch(/choose/i);
    expect(expectErrors(values({ departureDate: "2026-02-30" })).departureDate).toMatch(/real date/i);
  });

  test("a return date is not checked against an invalid departure", () => {
    const errors = expectErrors(values({ departureDate: "", returnDate: "2026-12-05" }));

    expect(errors.returnDate).toBeUndefined();
  });
});

describe("places and travellers", () => {
  test.each(["", "   "])("a blank place name %j is rejected", (blank) => {
    const errors = expectErrors(values({ origin: blank, destination: blank }));

    expect(errors.origin).toBeDefined();
    expect(errors.destination).toBeDefined();
  });

  test("place names are trimmed", () => {
    const request = expectOk(values({ origin: "  Indore ", destination: " Goa" }));

    expect(request.origin.name).toBe("Indore");
    expect(request.destination.name).toBe("Goa");
  });

  test("travellers become a list with one entry each and no ages", () => {
    const request = expectOk(values({ travellers: "3" }));

    expect(request.travellers).toEqual([{ age: null }, { age: null }, { age: null }]);
  });

  test.each(["", "0", "-1", "1.5", "abc", "1e3", " "])("travellers %j is rejected", (value) => {
    expect(expectErrors(values({ travellers: value })).travellers).toMatch(/at least 1/);
  });

  test("the owner's limit of 9 travellers is enforced and explained", () => {
    const atLimit = String(MAX_TRAVELLERS);
    const overLimit = String(MAX_TRAVELLERS + 1);

    expect(expectOk(values({ travellers: atLimit })).travellers).toHaveLength(
      MAX_TRAVELLERS,
    );
    expect(expectErrors(values({ travellers: overLimit })).travellers).toMatch(/at most 9 travellers/i);
  });
});

describe("the request matches the backend contract", () => {
  test("it has exactly the TripRequest fields and no budget", () => {
    const request = expectOk(values());

    expect(Object.keys(request).sort()).toEqual([
      "departure_date",
      "destination",
      "origin",
      "preferences",
      "return_date",
      "travellers",
      "trip_type",
    ]);
    expect(request.preferences).toBeNull();
  });

  test("it survives a JSON round trip unchanged", () => {
    const request = expectOk(values());

    expect(JSON.parse(JSON.stringify(request))).toEqual(request);
  });
});
