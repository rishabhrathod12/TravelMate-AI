import { describe, expect, test } from "vitest";

import {
  addMoney,
  formatMoney,
  minorUnitDigits,
  multiplyMoney,
  percentageRoundedUp,
  sumMoney,
} from "./money";

const inr = (amountMinor: number) => ({ amount_minor: amountMinor, currency: "INR" });

describe("formatMoney", () => {
  test("shows INR minor units as rupees with two decimals", () => {
    const text = formatMoney(inr(125_000));

    expect(text).toContain("₹");
    expect(text).toContain("1,250.00");
  });

  test("uses the currency's own number of minor-unit digits", () => {
    const yen = formatMoney({ amount_minor: 1500, currency: "JPY" });

    expect(yen).toContain("1,500");
    expect(yen).not.toContain(".");
  });

  test("refuses to show an amount that cannot be exact", () => {
    expect(formatMoney(inr(Number.MAX_SAFE_INTEGER + 2))).toBe("Amount unavailable");
  });

  test("does not throw on a malformed currency", () => {
    expect(formatMoney({ amount_minor: 100, currency: "XXXX" })).toBe("Amount unavailable");
  });
});

describe("minorUnitDigits", () => {
  test.each([
    ["INR", 2],
    ["USD", 2],
    ["JPY", 0],
    ["KWD", 3],
  ])("%s has %i digits", (currency, digits) => {
    expect(minorUnitDigits(currency)).toBe(digits);
  });
});

describe("integer arithmetic", () => {
  test("adds in the same currency", () => {
    expect(addMoney(inr(1), inr(2))).toEqual(inr(3));
  });

  test("refuses to add different currencies", () => {
    expect(() => addMoney(inr(1), { amount_minor: 1, currency: "USD" })).toThrow(/INR and USD/);
  });

  test("refuses a result that cannot be exact", () => {
    expect(() => addMoney(inr(Number.MAX_SAFE_INTEGER), inr(1))).toThrow(RangeError);
  });

  test("multiplies by a whole number", () => {
    expect(multiplyMoney(inr(600_000), 4)).toEqual(inr(2_400_000));
    expect(multiplyMoney(inr(5), 0)).toEqual(inr(0));
  });

  test.each([1.5, -1, Number.NaN])("refuses the factor %s", (factor) => {
    expect(() => multiplyMoney(inr(1), factor)).toThrow(RangeError);
  });

  test("sums a list, and an empty list is zero in the given currency", () => {
    expect(sumMoney([inr(1), inr(20), inr(300)], "INR")).toEqual(inr(321));
    expect(sumMoney([], "INR")).toEqual(inr(0));
  });
});

describe("percentageRoundedUp (the owner's contingency rounding)", () => {
  test("an exact result is not rounded further", () => {
    expect(percentageRoundedUp(inr(330), 1000)).toEqual(inr(33));
    expect(percentageRoundedUp(inr(2_700_000), 1000)).toEqual(inr(270_000));
  });

  test("any fraction of a minor unit rounds up to the next one", () => {
    expect(percentageRoundedUp(inr(333), 1000)).toEqual(inr(34)); // 33.3
    expect(percentageRoundedUp(inr(331), 1000)).toEqual(inr(34)); // 33.1
    expect(percentageRoundedUp(inr(1), 1000)).toEqual(inr(1)); // 0.1
  });

  test("zero stays zero", () => {
    expect(percentageRoundedUp(inr(0), 1000)).toEqual(inr(0));
    expect(percentageRoundedUp(inr(500), 0)).toEqual(inr(0));
  });

  test("the currency is kept", () => {
    expect(percentageRoundedUp({ amount_minor: 100, currency: "USD" }, 500).currency).toBe("USD");
  });

  test("a large amount is exact, with no loss of precision", () => {
    const big = 2 ** 52 + 1; // odd, near the safe limit
    // 10% of an odd number ending in 3 is x.3, so the answer is the next integer.
    expect(percentageRoundedUp(inr(big), 1000).amount_minor).toBe(Math.floor(big / 10) + 1);
  });

  test("refuses a negative amount, a negative or fractional rate, and an unsafe amount", () => {
    expect(() => percentageRoundedUp(inr(-1), 1000)).toThrow(RangeError);
    expect(() => percentageRoundedUp(inr(100), -1)).toThrow(RangeError);
    expect(() => percentageRoundedUp(inr(100), 0.5)).toThrow(RangeError);
    expect(() => percentageRoundedUp(inr(2 ** 60), 1000)).toThrow(RangeError);
  });
});
