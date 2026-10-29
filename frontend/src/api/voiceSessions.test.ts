import { afterEach, describe, expect, test, vi } from "vitest";

import {
  createVoiceSession,
  endVoiceSession,
  readVoiceSession,
  recordVoiceActivity,
  VoiceApiError,
} from "./voiceSessions";

const INFO = {
  session_id: "abc_DEF-123",
  expires_at: "2026-12-01T09:10:00Z",
  max_seconds: 600,
  idle_timeout_seconds: 120,
  provider: null,
  notice: "No voice provider is connected.",
};

/** Each call gets a fresh Response (a body can be read only once) or a rejection. */
function stubFetch(next: () => Response | Error) {
  const spy = vi.fn<typeof fetch>(() => {
    const result = next();
    // A DOMException is not always an `Error` here, so test for the Response instead.
    return result instanceof Response ? Promise.resolve(result) : Promise.reject(result);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the requests", () => {
  test("create posts to the sessions collection and returns the typed session", async () => {
    const spy = stubFetch(() => json(INFO, 201));

    const info = await createVoiceSession();

    expect(info).toEqual(INFO);
    expect(spy).toHaveBeenCalledWith(
      "/api/v1/voice/sessions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("read, activity and end use the right method and path, with the id encoded", async () => {
    const spy = stubFetch(() => json(INFO));

    await readVoiceSession("a/b c");
    await recordVoiceActivity("a/b c");
    spy.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await endVoiceSession("a/b c");

    const calls = spy.mock.calls.map(([url, init]) => [(init as RequestInit).method, url]);
    expect(calls).toEqual([
      ["GET", "/api/v1/voice/sessions/a%2Fb%20c"],
      ["POST", "/api/v1/voice/sessions/a%2Fb%20c/activity"],
      ["DELETE", "/api/v1/voice/sessions/a%2Fb%20c"],
    ]);
  });

  test("sends no body, no credentials and no audio or text", async () => {
    const spy = stubFetch(() => json(INFO, 201));

    await createVoiceSession();

    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBeUndefined();
    expect(init.credentials).toBeUndefined();
    expect(Object.keys(init.headers as Record<string, string>)).toEqual(["Accept"]);
  });
});

describe("the answers", () => {
  test("a Problem Details body gives the status and the server's own explanation", async () => {
    stubFetch(() =>
      json(
        {
          title: "Voice session limit reached",
          detail: "the daily voice session limit has been reached",
        },
        429,
      ),
    );

    await expect(createVoiceSession()).rejects.toMatchObject({
      status: 429,
      detail: "the daily voice session limit has been reached",
    });
  });

  test("an error with no readable body has no detail", async () => {
    stubFetch(() => new Response("<html>nope</html>", { status: 404 }));

    await expect(readVoiceSession("x")).rejects.toMatchObject({ status: 404, detail: null });
  });

  test("an unreachable server is an error with no status", async () => {
    stubFetch(() => new TypeError("Failed to fetch"));

    const error = await createVoiceSession().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(VoiceApiError);
    expect((error as VoiceApiError).status).toBeNull();
  });

  test("an answer of the wrong shape is rejected instead of trusted", async () => {
    stubFetch(() => json({ session_id: "x" }, 201));

    await expect(createVoiceSession()).rejects.toBeInstanceOf(VoiceApiError);
  });

  test("a session that claims a provider is rejected, because none exists", async () => {
    stubFetch(() => json({ ...INFO, provider: "some-vendor" }, 201));

    await expect(createVoiceSession()).rejects.toBeInstanceOf(VoiceApiError);
  });

  test("an aborted request surfaces the abort, not a server error", async () => {
    const controller = new AbortController();
    controller.abort();
    stubFetch(() => new DOMException("aborted", "AbortError") as unknown as Error);

    const error = await createVoiceSession(controller.signal).catch((e: unknown) => e);

    expect(error).not.toBeInstanceOf(VoiceApiError);
  });
});
