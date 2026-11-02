import { describe, expect, test } from "vitest";

import { parseRoute, ROUTES } from "./route";

describe("parseRoute", () => {
  test.each([
    ["#/plan", "plan"],
    ["#/form", "form"],
    ["#/trips", "trips"],
    ["#/about", "about"],
  ])("%s opens %s", (hash, route) => {
    expect(parseRoute(hash)).toBe(route);
  });

  test.each(["", "#", "#/", "#/unknown", "#main", "#demo-train-1"])(
    "%j falls back to the planning page",
    (hash) => {
      expect(parseRoute(hash)).toBe("plan");
    },
  );

  test("every navigation link leads to its own route", () => {
    for (const item of ROUTES) {
      expect(parseRoute(item.href)).toBe(item.route);
    }
  });

  test("the navigation has the three views from the brief, plus the trip form", () => {
    expect(ROUTES.map((item) => item.label)).toEqual(["Plan Trip", "Trip Form", "My Trips", "About"]);
  });
});
