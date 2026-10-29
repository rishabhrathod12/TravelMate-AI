import { describe, expect, test } from "vitest";

import type { TransportOption } from "../contracts/types";
import { buildDemoOptions } from "../demo/demoData";
import { EXAMPLE_FORM, validateTripForm } from "./tripRequest";
import {
  durationMinutes,
  groupByMode,
  modeSpecificFact,
  quotedTotal,
  sortTransport,
  transportFacts,
} from "./transport";

const validated = validateTripForm(EXAMPLE_FORM);
if (!validated.ok) {
  throw new Error("The example trip must be valid");
}
const demo = buildDemoOptions(validated.request);
const byLabel = (label: string): TransportOption => {
  const found = demo.transport.find((option) => option.service_label === label);
  if (found === undefined) {
    throw new Error(`No demo service ${label}`);
  }
  return found;
};

describe("sortTransport", () => {
  test("by price puts the cheapest first and a missing price last, never as zero", () => {
    const noPrice: TransportOption = { ...byLabel("DEMO-T201"), id: "x-no-price", price: null };
    const sorted = sortTransport([...demo.transport, noPrice], "price");

    expect(sorted[0]?.service_label).toBe("DEMO-T202");
    expect(sorted.at(-1)?.id).toBe("x-no-price");
  });

  test("by duration puts the shortest first", () => {
    const sorted = sortTransport(demo.transport, "duration");

    expect(sorted[0]?.mode).toBe("FLIGHT");
    expect(durationMinutes(sorted[0] as TransportOption)).toBeLessThanOrEqual(
      durationMinutes(sorted[1] as TransportOption),
    );
  });

  test("does not change the list it is given", () => {
    const before = demo.transport.map((option) => option.id);

    sortTransport(demo.transport, "price");

    expect(demo.transport.map((option) => option.id)).toEqual(before);
  });

  test("equal values keep a stable order by id", () => {
    const a: TransportOption = { ...byLabel("DEMO-T201"), id: "a" };
    const b: TransportOption = { ...byLabel("DEMO-T201"), id: "b" };

    expect(sortTransport([b, a], "price").map((o) => o.id)).toEqual(["a", "b"]);
  });
});

describe("groupByMode", () => {
  test("gives flights, trains and buses in that order, only the modes that have options", () => {
    expect(groupByMode(demo.transport).map((group) => [group.mode, group.options.length])).toEqual([
      ["FLIGHT", 3],
      ["TRAIN", 2],
      ["BUS", 2],
    ]);
    expect(groupByMode(demo.transport.filter((o) => o.mode === "BUS")).map((g) => g.mode)).toEqual([
      "BUS",
    ]);
    expect(groupByMode([])).toEqual([]);
  });
});

describe("transportFacts shows only what fits the mode", () => {
  const labels = (option: TransportOption) => transportFacts(option).map((fact) => fact.label);

  test("a flight shows stops and cabin class, not train class or seat type", () => {
    expect(labels(byLabel("DEMO-F102"))).toEqual([
      "Operator",
      "Service",
      "Departs",
      "Arrives",
      "Duration",
      "Stops",
      "Cabin class",
      "Cancellation",
    ]);
  });

  test("a train shows stops and class", () => {
    expect(labels(byLabel("DEMO-T201"))).toContain("Class");
    expect(labels(byLabel("DEMO-T201"))).not.toContain("Cabin class");
    expect(labels(byLabel("DEMO-T201"))).toContain("Stops");
  });

  test("a bus shows seat type, and shows stops only when they are known", () => {
    expect(labels(byLabel("DEMO-B301"))).not.toContain("Stops");
    expect(labels(byLabel("DEMO-B302"))).toContain("Stops");
    expect(labels(byLabel("DEMO-B302"))).toContain("Seat type");
    expect(labels(byLabel("DEMO-B302"))).not.toContain("Class");
  });

  test("a missing fact reads Not supplied instead of a blank or a zero", () => {
    const facts = Object.fromEntries(transportFacts(byLabel("DEMO-F103")).map((f) => [f.label, f.value]));

    expect(facts["Cabin class"]).toBe("Not supplied");
    expect(facts["Cancellation"]).toBe("Not supplied");
    expect(facts["Stops"]).toBe("1");
  });

  test("zero stops is shown as 0, not as missing", () => {
    const facts = Object.fromEntries(transportFacts(byLabel("DEMO-F102")).map((f) => [f.label, f.value]));

    expect(facts["Stops"]).toBe("0");
  });

  test("the mode-specific fact is named per mode", () => {
    expect(modeSpecificFact(byLabel("DEMO-F101"))?.label).toBe("Cabin class");
    expect(modeSpecificFact(byLabel("DEMO-T201"))?.label).toBe("Class");
    expect(modeSpecificFact(byLabel("DEMO-B302"))?.label).toBe("Seat type");
    expect(modeSpecificFact({ ...byLabel("DEMO-B302"), mode: "ROAD", details: null })).toBeNull();
  });
});

describe("quotedTotal", () => {
  test("is the price plus the fees, in whole minor units", () => {
    const train = byLabel("DEMO-T201");

    expect(quotedTotal(train, demo.quotes[train.id])?.amount_minor).toBe(150_000 + 5_000);
  });

  test("with no quote it is just the price", () => {
    const train = byLabel("DEMO-T201");

    expect(quotedTotal(train, undefined)?.amount_minor).toBe(150_000);
  });

  test("is null when there is no price, and when the currencies differ", () => {
    const train = byLabel("DEMO-T201");
    const quote = demo.quotes[train.id];
    if (quote === undefined) {
      throw new Error("expected a quote");
    }

    expect(quotedTotal({ ...train, price: null }, quote)).toBeNull();
    expect(
      quotedTotal(train, {
        ...quote,
        fees: [{ label: "x", amount: { amount_minor: 1, currency: "USD" } }],
      }),
    ).toBeNull();
  });
});
