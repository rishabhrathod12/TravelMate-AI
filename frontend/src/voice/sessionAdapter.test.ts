import { afterEach, describe, expect, test, vi } from "vitest";

import { VoiceApiError, type VoiceSessionApi, type VoiceSessionInfo } from "../api/voiceSessions";
import { NO_ASSISTANT_NOTICE, createSessionOnlyAdapter } from "./sessionAdapter";
import type { AdapterEvent } from "./VoiceAdapter";

const INFO: VoiceSessionInfo = {
  session_id: "session-1",
  expires_at: "2026-12-01T09:10:00Z",
  max_seconds: 600,
  idle_timeout_seconds: 120,
  provider: null,
  notice: "No voice provider is connected.",
};

function fakeApi(overrides: Partial<VoiceSessionApi> = {}) {
  const api = {
    create: vi.fn(() => Promise.resolve(INFO)),
    read: vi.fn(() => Promise.resolve(INFO)),
    activity: vi.fn(() => Promise.resolve(INFO)),
    end: vi.fn(() => Promise.resolve()),
    ...overrides,
  };
  return api satisfies VoiceSessionApi;
}

async function connected(api = fakeApi(), pollMs = 1_000) {
  const events: AdapterEvent[] = [];
  const adapter = createSessionOnlyAdapter({ api, pollMs });
  await adapter.connect({ microphone: true }, (event) => events.push(event));
  return { adapter, api, events };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("what it claims", () => {
  test("it is not a mock and says it hears and plays nothing", () => {
    const adapter = createSessionOnlyAdapter({ api: fakeApi() });

    expect(adapter.isMock).toBe(false);
    expect(adapter.hearsUser).toBe(false);
    expect(adapter.playsAudio).toBe(false);
    expect(adapter.devControls).toBeUndefined();
    expect(adapter.audioDisclosure).toMatch(/No audio is captured, recorded or sent anywhere/);
  });

  test("it never asks the browser for the microphone, even when a voice session is requested", async () => {
    const getUserMedia = vi.fn();
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });

    await connected();

    expect(getUserMedia).not.toHaveBeenCalled();
  });
});

describe("opening and closing a session", () => {
  test("connect opens one session on the server", async () => {
    const { api } = await connected();

    expect(api.create).toHaveBeenCalledTimes(1);
  });

  test("disconnect ends that session on the server, once", async () => {
    const { adapter, api } = await connected();

    adapter.disconnect();
    adapter.disconnect();

    expect(api.end).toHaveBeenCalledTimes(1);
    expect(api.end).toHaveBeenCalledWith("session-1");
  });

  test("a failure to end the session on the server is not an error for the user", async () => {
    const api = fakeApi({ end: vi.fn(() => Promise.reject(new VoiceApiError(null, null))) });
    const { adapter } = await connected(api);

    expect(() => adapter.disconnect()).not.toThrow();
    await Promise.resolve();
  });

  test("closing while the session is still being opened leaves nothing behind", async () => {
    let finish: (info: VoiceSessionInfo) => void = () => undefined;
    const api = fakeApi({ create: vi.fn(() => new Promise<VoiceSessionInfo>((r) => (finish = r))) });
    const adapter = createSessionOnlyAdapter({ api });
    const opening = adapter.connect({ microphone: false }, () => undefined);
    const assertion = expect(opening).rejects.toMatchObject({ code: "connection" });

    adapter.disconnect();
    finish(INFO);
    await assertion;

    expect(api.end).toHaveBeenCalledWith("session-1");
  });
});

describe("when opening fails", () => {
  const failing = (status: number | null, detail: string | null = null) =>
    fakeApi({ create: vi.fn(() => Promise.reject(new VoiceApiError(status, detail))) });

  async function codeFor(api: ReturnType<typeof failing>) {
    const adapter = createSessionOnlyAdapter({ api });
    return adapter.connect({ microphone: true }, () => undefined).catch((e: unknown) => e);
  }

  test("a server with voice switched off (404) is 'unavailable'", async () => {
    expect(await codeFor(failing(404))).toMatchObject({
      code: "unavailable",
      message: expect.stringContaining("turned off"),
    });
  });

  test("an unreachable server is 'unavailable'", async () => {
    expect(await codeFor(failing(null))).toMatchObject({
      code: "unavailable",
      message: expect.stringContaining("could not be reached"),
    });
  });

  test("a limit (429) is 'limit_reached' and carries the server's explanation", async () => {
    expect(await codeFor(failing(429, "the active voice session limit has been reached"))).toMatchObject({
      code: "limit_reached",
      message: "the active voice session limit has been reached",
    });
  });

  test("anything else is 'unknown'", async () => {
    expect(await codeFor(failing(500))).toMatchObject({ code: "unknown" });
  });
});

describe("watching the session", () => {
  test("a session the server no longer has is reported once as ended", async () => {
    vi.useFakeTimers();
    const api = fakeApi({ read: vi.fn(() => Promise.reject(new VoiceApiError(410, null))) });
    const { events } = await connected(api, 1_000);

    await vi.advanceTimersByTimeAsync(5_000);

    expect(events).toEqual([
      {
        type: "error",
        code: "session_expired",
        message: "The voice session has ended. Start a new one.",
      },
    ]);
  });

  test("losing the server is reported as a connection problem", async () => {
    vi.useFakeTimers();
    const api = fakeApi({ read: vi.fn(() => Promise.reject(new VoiceApiError(null, null))) });
    const { events } = await connected(api, 1_000);

    await vi.advanceTimersByTimeAsync(1_500);

    expect(events).toMatchObject([{ type: "error", code: "connection" }]);
  });

  test("a healthy session stays quiet, and checking is not counted as activity", async () => {
    vi.useFakeTimers();
    const { api, events } = await connected(fakeApi(), 1_000);

    await vi.advanceTimersByTimeAsync(3_500);

    expect(api.read).toHaveBeenCalledTimes(3);
    expect(api.activity).not.toHaveBeenCalled();
    expect(events).toEqual([]);
  });

  test("it stops checking after the session is closed", async () => {
    vi.useFakeTimers();
    const { adapter, api } = await connected(fakeApi(), 1_000);
    await vi.advanceTimersByTimeAsync(1_500);

    adapter.disconnect();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(api.read).toHaveBeenCalledTimes(1);
  });
});

describe("typed messages", () => {
  test("record activity on the server, then answer with a plain notice and not as an assistant", async () => {
    const { adapter, api, events } = await connected();

    adapter.sendText("hello");
    await vi.waitFor(() => expect(events.at(-1)).toEqual({ type: "listening" }));

    expect(api.activity).toHaveBeenCalledWith("session-1");
    expect(events).toEqual([
      { type: "thinking" },
      { type: "transcript", speaker: "assistant", text: NO_ASSISTANT_NOTICE, source: "notice" },
      { type: "listening" },
    ]);
  });

  test("the text itself is never sent to the server", async () => {
    const { adapter, api } = await connected();

    adapter.sendText("my secret plan");
    await vi.waitFor(() => expect(api.activity).toHaveBeenCalled());

    expect(JSON.stringify(vi.mocked(api.activity).mock.calls)).not.toContain("secret");
  });

  test("a session that has ended while the user typed is reported, with no notice", async () => {
    const api = fakeApi({ activity: vi.fn(() => Promise.reject(new VoiceApiError(404, null))) });
    const { adapter, events } = await connected(api);

    adapter.sendText("hello");
    await vi.waitFor(() => expect(events.some((e) => e.type === "error")).toBe(true));

    expect(events.some((e) => e.type === "transcript")).toBe(false);
    expect(events.at(-1)).toMatchObject({ code: "session_expired" });
  });

  test("with no open session, typing does nothing", () => {
    const events: AdapterEvent[] = [];
    const adapter = createSessionOnlyAdapter({ api: fakeApi() });

    adapter.sendText("hello");

    expect(events).toEqual([]);
  });
});
