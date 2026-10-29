import { describe, expect, test } from "vitest";

import { stubFetchResponse, stubHealthDown, stubHealthOk } from "../test/mockFetch";
import { fetchHealth } from "./health";

describe("fetchHealth", () => {
  test("returns the health body and asks for JSON from /health", async () => {
    const fetchMock = stubHealthOk();

    const health = await fetchHealth();

    expect(health).toEqual({ status: "ok", service: "travelmate-ai", version: "0.1.0" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/health");
    expect(init.headers).toEqual({ Accept: "application/json" });
  });

  test("rejects a non-success status", async () => {
    stubFetchResponse({ detail: "down" }, 503);

    await expect(fetchHealth()).rejects.toThrow(/HTTP 503/);
  });

  test.each([
    ["a wrong status value", { status: "degraded", service: "x", version: "1" }],
    ["a missing field", { status: "ok", service: "x" }],
    ["a non-object", "ok"],
    ["null", null],
  ])("rejects %s", async (_name, body) => {
    stubFetchResponse(body);

    await expect(fetchHealth()).rejects.toThrow(/expected shape/);
  });

  test("passes a network failure through", async () => {
    stubHealthDown();

    await expect(fetchHealth()).rejects.toThrow(/Failed to fetch/);
  });
});
