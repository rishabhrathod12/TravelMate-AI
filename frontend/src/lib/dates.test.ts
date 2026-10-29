import { describe, expect, test } from "vitest";

import {
  addDays,
  daysBetween,
  formatDay,
  formatDuration,
  formatUtcDateTime,
  isValidIsoDate,
  parseIsoDate,
} from "./dates";

describe("parseIsoDate", () => {
  test("accepts real calendar dates, including a leap day", () => {
    expect(isValidIsoDate("2026-12-01")).toBe(true);
    expect(isValidIsoDate("2028-02-29")).toBe(true);
  });

  test.each(["", "2026-02-30", "2026-13-01", "2027-02-29", "26-01-01", "2026-1-1", "2026-12-01T00:00"])(
    "rejects %j",
    (value) => {
      expect(parseIsoDate(value)).toBeNull();
    },
  );
});

describe("date arithmetic", () => {
  test("counts whole days, forwards and backwards", () => {
    expect(daysBetween("2026-12-01", "2026-12-05")).toBe(4);
    expect(daysBetween("2026-12-01", "2026-12-01")).toBe(0);
    expect(daysBetween("2026-12-05", "2026-12-01")).toBe(-4);
  });

  test("adds days across month, year and leap-day boundaries", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2026-12-01", 0)).toBe("2026-12-01");
  });

  test("throws on a date that does not exist", () => {
    expect(() => daysBetween("2026-02-30", "2026-03-01")).toThrow(RangeError);
  });
});

describe("formatting", () => {
  test("formats a calendar day in UTC", () => {
    expect(formatDay("2026-12-01")).toContain("1 Dec 2026");
  });

  test("formats a timestamp in UTC and says so", () => {
    const text = formatUtcDateTime("2026-12-01T04:00:00Z");

    expect(text).toContain("1 Dec 2026");
    expect(text).toContain("04:00");
    expect(text.endsWith("UTC")).toBe(true);
  });

  test("a time with an offset is converted to UTC", () => {
    expect(formatUtcDateTime("2026-12-01T09:30:00+05:30")).toContain("04:00");
  });

  test("an unreadable timestamp is reported, not guessed", () => {
    expect(formatUtcDateTime("not a time")).toBe("Unknown time");
  });

  test.each([
    ["2026-12-01T04:00:00Z", "2026-12-01T16:30:00Z", "12h 30m"],
    ["2026-12-01T08:00:00Z", "2026-12-01T08:45:00Z", "45m"],
    ["2026-12-01T08:00:00Z", "2026-12-01T07:00:00Z", "Unknown duration"],
  ])("duration from %s to %s is %s", (start, end, expected) => {
    expect(formatDuration(start, end)).toBe(expected);
  });
});
