import { describe, expect, test } from "vitest";

import { addMoney, formatMoney, minorUnitDigits, multiplyMoney, sumMoney } from "./money";

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
