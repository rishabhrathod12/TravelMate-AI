import type { Money } from "../contracts/types";

/**
 * Money helpers. Arithmetic works on integer minor units only. Division by the
 * currency's minor-unit factor happens once, for display, and never feeds back
 * into a calculation.
 */

/** Number of minor-unit digits of a currency (2 for INR, 0 for JPY), from the browser's data. */
export function minorUnitDigits(currency: string): number {
  const options = new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions();
  return options.maximumFractionDigits ?? 2;
}

export function formatMoney(money: Money, locale = "en-IN"): string {
  // amount_minor can reach 2^63 in the backend; JavaScript numbers are exact only to 2^53.
  if (!Number.isSafeInteger(money.amount_minor)) {
    return "Amount unavailable";
  }
  try {
    const digits = minorUnitDigits(money.currency);
    return new Intl.NumberFormat(locale, { style: "currency", currency: money.currency }).format(
      money.amount_minor / 10 ** digits,
    );
  } catch {
    return "Amount unavailable";
  }
}

function assertSafe(amountMinor: number): number {
  if (!Number.isSafeInteger(amountMinor)) {
    throw new RangeError("Amount is too large for exact arithmetic");
  }
  return amountMinor;
}

export function addMoney(a: Money, b: Money): Money {
  if (a.currency !== b.currency) {
    throw new Error(`Cannot add ${a.currency} and ${b.currency}`);
  }
  return { amount_minor: assertSafe(a.amount_minor + b.amount_minor), currency: a.currency };
}

export function multiplyMoney(money: Money, factor: number): Money {
  if (!Number.isInteger(factor) || factor < 0) {
    throw new RangeError("Factor must be a non-negative integer");
  }
  return { amount_minor: assertSafe(money.amount_minor * factor), currency: money.currency };
}

/**
 * `basisPoints` hundredths of a percent of `money`, rounded up to the next minor unit (the owner's
 * contingency rounding, Q18). Exact: it uses BigInt, so a large amount cannot lose precision.
 */
export function percentageRoundedUp(money: Money, basisPoints: number): Money {
  if (!Number.isInteger(basisPoints) || basisPoints < 0) {
    throw new RangeError("Basis points must be a non-negative integer");
  }
  if (money.amount_minor < 0) {
    throw new RangeError("Amount must not be negative");
  }
  assertSafe(money.amount_minor);
  const product = BigInt(money.amount_minor) * BigInt(basisPoints);
  const rounded = (product + 9_999n) / 10_000n;
  return { amount_minor: assertSafe(Number(rounded)), currency: money.currency };
}

export function sumMoney(items: readonly Money[], currency: string): Money {
  return items.reduce(addMoney, { amount_minor: 0, currency });
}
