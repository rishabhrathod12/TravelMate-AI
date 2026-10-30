import { describe, expect, test } from "vitest";

import type { ItineraryRequest } from "../contracts/types";
import { buildSamplePlan } from "./sampleItinerary";

function request(days: number): ItineraryRequest {
  return {
    destination: { name: "Goa" },
    start_date: "2026-11-07",
    days,
    travellers: null,
    preferences: null,
  };
}

describe("buildSamplePlan", () => {
  test("has one entry per requested day, numbered from 1", () => {
    const plan = buildSamplePlan(request(5));

    expect(plan.map((day) => day.day_number)).toEqual([1, 2, 3, 4, 5]);
  });

  test("every line is labelled as a scripted sample, never as an AI suggestion", () => {
    const labels = buildSamplePlan(request(4)).flatMap((day) => day.items.map((i) => i.label));

    expect(labels.length).toBeGreaterThan(0);
    expect(new Set(labels)).toEqual(new Set(["SCRIPTED_SAMPLE"]));
  });

  test("names the destination but no activity, price, time or booking", () => {
    const text = buildSamplePlan(request(3))
      .flatMap((day) => day.items.map((item) => item.title))
      .join(" ");

    expect(text).toContain("Goa");
    expect(text).not.toMatch(/\d/); // no prices, times or counts
    expect(text).not.toMatch(/book|ticket|pay|₹|rs\b/i);
  });

  test("the first day is an arrival and the last day is a departure", () => {
    const plan = buildSamplePlan(request(3));

    expect(plan[0]?.items[0]?.title).toMatch(/Arrive in Goa/);
    expect(plan[2]?.items.at(-1)?.title).toMatch(/Head home/);
  });

  test("a one-day plan is a single day", () => {
    const plan = buildSamplePlan(request(1));

    expect(plan).toHaveLength(1);
    expect(plan[0]?.items.map((i) => i.title)).toEqual(["A day in Goa", "Head home"]);
  });
});
