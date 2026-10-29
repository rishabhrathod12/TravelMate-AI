import { vi } from "vitest";

/** Test helpers that replace `fetch`, so no test touches the network. */

export const HEALTH_BODY = { status: "ok", service: "travelmate-ai", version: "0.1.0" };

export function stubHealthOk() {
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(HEALTH_BODY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function stubHealthDown() {
  const fetchMock = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function stubFetchResponse(body: unknown, status = 200) {
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
