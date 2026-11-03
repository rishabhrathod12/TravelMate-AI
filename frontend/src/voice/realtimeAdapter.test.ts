import { describe, expect, test, vi } from "vitest";

import { VoiceApiError, type RealtimeConnection, type RealtimeVoiceApi } from "../api/voiceSessions";
import {
  createRealtimeAdapter,
  eventFromMessage,
  EVENTS_CHANNEL,
  OPENAI_CALLS_URL,
  REALTIME_DISCLOSURE,
  type RtcAudio,
  type RtcChannel,
  type RtcEnvironment,
  type RtcPeer,
  type RtcStream,
  type RtcTrack,
} from "./realtimeAdapter";
import { VoiceConnectionError, type AdapterEvent } from "./VoiceAdapter";

const SECRET = "ek_fake_secret_for_tests_only";
const SESSION = "s".repeat(43);

const GRANT: RealtimeConnection = {
  session_id: SESSION,
  client_secret: SECRET,
  secret_expires_at: "2026-11-03T09:01:00Z",
  model: "test-realtime-model",
  voice: "test-voice",
  max_seconds: 600,
  notice: "Live voice (development build).",
};

class FakeTrack implements RtcTrack {
  enabled = true;
  stopped = false;
  stop() {
    this.stopped = true;
  }
}

class FakeChannel implements RtcChannel {
  readyState = "open";
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: Record<string, unknown>[] = [];
  closed = false;
  send(data: string) {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close() {
    this.closed = true;
  }
}

class FakePeer implements RtcPeer {
  ontrack: RtcPeer["ontrack"] = null;
  onconnectionstatechange: (() => void) | null = null;
  connectionState = "new";
  tracks: RtcTrack[] = [];
  channels: FakeChannel[] = [];
  labels: string[] = [];
  local: { type: string; sdp?: string } | null = null;
  remote: { type: string; sdp: string } | null = null;
  closed = false;
  addTrack(track: RtcTrack) {
    this.tracks.push(track);
  }
  createDataChannel(label: string) {
    this.labels.push(label);
    const channel = new FakeChannel();
    this.channels.push(channel);
    return channel;
  }
  async createOffer() {
    return { type: "offer", sdp: "v=0 offer" };
  }
  async setLocalDescription(description: { type: string; sdp?: string }) {
    this.local = description;
  }
  async setRemoteDescription(description: { type: string; sdp: string }) {
    this.remote = description;
  }
  close() {
    this.closed = true;
  }
}

interface Rig {
  env: RtcEnvironment;
  peer: FakePeer;
  track: FakeTrack;
  audio: RtcAudio & { paused: boolean };
  fetches: { url: string; init: { method: string; headers: Record<string, string>; body: string } }[];
  timers: { callback: () => void; ms: number }[];
  getUserMedia: ReturnType<typeof vi.fn>;
}

function rig(options: { micError?: { name: string }; answer?: { ok: boolean; status: number; text: string } } = {}): Rig {
  const peer = new FakePeer();
  const track = new FakeTrack();
  const stream: RtcStream = { getTracks: () => [track] };
  const audio = { autoplay: false, srcObject: null as unknown, paused: false, pause() { this.paused = true; } };
  const fetches: Rig["fetches"] = [];
  const timers: Rig["timers"] = [];
  const answer = options.answer ?? { ok: true, status: 201, text: "v=0 answer" };
  const getUserMedia = vi.fn(async () => {
    if (options.micError) {
      throw options.micError;
    }
    return stream;
  });
  const env: RtcEnvironment = {
    getUserMedia,
    createPeer: () => peer,
    createAudio: () => audio,
    fetchText: async (url, init) => {
      fetches.push({ url, init });
      return { ok: answer.ok, status: answer.status, text: async () => answer.text };
    },
    setTimer: (callback, ms) => {
      timers.push({ callback, ms });
      return timers.length;
    },
    clearTimer: () => undefined,
  };
  return { env, peer, track, audio, fetches, timers, getUserMedia };
}

function fakeApi(overrides: Partial<RealtimeVoiceApi> = {}): RealtimeVoiceApi & {
  created: number;
  ended: string[];
} {
  const state = { created: 0, ended: [] as string[] };
  return {
    get created() {
      return state.created;
    },
    get ended() {
      return state.ended;
    },
    create: async () => {
      state.created += 1;
      return {
        session_id: SESSION,
        expires_at: "2026-11-03T09:10:00Z",
        max_seconds: 600,
        idle_timeout_seconds: 120,
        provider: null,
        notice: "n",
      };
    },
    realtime: async () => GRANT,
    end: async (id) => {
      state.ended.push(id);
    },
    ...overrides,
  };
}

function collect() {
  const events: AdapterEvent[] = [];
  return { events, listener: (event: AdapterEvent) => events.push(event) };
}

describe("what the adapter says it is", () => {
  test("it hears and plays, is not a mock, and discloses where the audio goes", () => {
    const adapter = createRealtimeAdapter({ api: fakeApi(), env: rig().env });

    expect(adapter.isMock).toBe(false);
    expect(adapter.hearsUser).toBe(true);
    expect(adapter.playsAudio).toBe(true);
    expect(adapter.devControls).toBeUndefined();
    expect(adapter.audioDisclosure).toBe(REALTIME_DISCLOSURE);
    expect(REALTIME_DISCLOSURE).toMatch(/sent to OpenAI/);
    expect(REALTIME_DISCLOSURE).toMatch(/cannot search, book or approve/);
  });
});

describe("opening a session", () => {
  test("it opens the server session, then the microphone, then one connection to OpenAI", async () => {
    const r = rig();
    const api = fakeApi();
    const { events, listener } = collect();

    await createRealtimeAdapter({ api, env: r.env }).connect({ microphone: true }, listener);

    expect(api.created).toBe(1);
    expect(r.getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(r.peer.labels).toEqual([EVENTS_CHANNEL]);
    expect(r.peer.tracks).toEqual([r.track]);
    expect(r.fetches).toHaveLength(1);
    expect(r.fetches[0]?.url).toBe(OPENAI_CALLS_URL);
    expect(r.fetches[0]?.init.method).toBe("POST");
    expect(r.fetches[0]?.init.headers["Content-Type"]).toBe("application/sdp");
    expect(r.fetches[0]?.init.headers.Authorization).toBe(`Bearer ${SECRET}`);
    expect(r.fetches[0]?.init.body).toBe("v=0 offer");
    expect(r.peer.local?.type).toBe("offer");
    expect(r.peer.remote).toEqual({ type: "answer", sdp: "v=0 answer" });
    expect(r.audio.autoplay).toBe(true);
    expect(events).toEqual([{ type: "listening" }]);
  });

  test("the microphone is not asked for until the server has agreed to a session", async () => {
    const r = rig();
    const api = fakeApi({
      create: async () => {
        throw new VoiceApiError(429, "limit");
      },
    });

    await expect(
      createRealtimeAdapter({ api, env: r.env }).connect({ microphone: true }, () => undefined),
    ).rejects.toMatchObject({ code: "limit_reached" });

    expect(r.getUserMedia).not.toHaveBeenCalled();
    expect(r.fetches).toHaveLength(0);
  });

  test("a text-only session opens no microphone", async () => {
    const r = rig();

    await createRealtimeAdapter({ api: fakeApi(), env: r.env }).connect({ microphone: false }, () => undefined);

    expect(r.getUserMedia).not.toHaveBeenCalled();
    expect(r.peer.tracks).toEqual([]);
    expect(r.fetches).toHaveLength(1);
  });

  test("it sends no session settings and no tools: only the offer goes to OpenAI", async () => {
    const r = rig();

    await createRealtimeAdapter({ api: fakeApi(), env: r.env }).connect({ microphone: true }, () => undefined);

    expect(r.peer.channels[0]?.sent).toEqual([]);
    expect(r.fetches[0]?.init.body).not.toMatch(/tools|instructions/);
  });
});

describe("when opening fails", () => {
  test("a blocked microphone is reported as such, and the server session is ended", async () => {
    const r = rig({ micError: { name: "NotAllowedError" } });
    const api = fakeApi();

    await expect(
      createRealtimeAdapter({ api, env: r.env }).connect({ microphone: true }, () => undefined),
    ).rejects.toMatchObject({ code: "permission_denied" });

    expect(api.ended).toEqual([SESSION]);
    expect(r.fetches).toHaveLength(0);
  });

  test("no microphone at all is reported as such", async () => {
    const r = rig({ micError: { name: "NotFoundError" } });

    await expect(
      createRealtimeAdapter({ api: fakeApi(), env: r.env }).connect({ microphone: true }, () => undefined),
    ).rejects.toMatchObject({ code: "no_microphone" });
  });

  test.each([
    [404, "unavailable", /turned off/],
    [429, "limit_reached", /limit/],
    [502, "unavailable", /could not start/],
  ])("a server answer %i gives a clear message", async (status, code, message) => {
    const api = fakeApi({
      realtime: async () => {
        throw new VoiceApiError(status, "The hour's limit is used up.");
      },
    });

    const failure = createRealtimeAdapter({ api, env: rig().env }).connect({ microphone: false }, () => undefined);

    await expect(failure).rejects.toMatchObject({ code });
    await expect(failure).rejects.toThrow(message);
  });

  test("OpenAI refusing the connection is reported without its own words, and cleans up", async () => {
    const r = rig({ answer: { ok: false, status: 401, text: "invalid api key sk-leak" } });
    const api = fakeApi();

    const failure = createRealtimeAdapter({ api, env: r.env }).connect({ microphone: true }, () => undefined);

    await expect(failure).rejects.toBeInstanceOf(VoiceConnectionError);
    await expect(failure).rejects.not.toThrow(/401|sk-leak|invalid api key/);
    expect(r.peer.closed).toBe(true);
    expect(r.track.stopped).toBe(true);
    expect(api.ended).toEqual([SESSION]);
  });

  test("the secret is never in an error message", async () => {
    const r = rig({ answer: { ok: false, status: 500, text: "" } });

    const failure = createRealtimeAdapter({ api: fakeApi(), env: r.env }).connect({ microphone: true }, () => undefined);

    await expect(failure).rejects.not.toThrow(SECRET);
  });
});

describe("during a session", () => {
  async function open() {
    const r = rig();
    const api = fakeApi();
    const { events, listener } = collect();
    const adapter = createRealtimeAdapter({ api, env: r.env });
    await adapter.connect({ microphone: true }, listener);
    events.length = 0;
    return { adapter, r, api, events };
  }

  test("muting turns the microphone track off and on", async () => {
    const { adapter, r } = await open();

    adapter.setMuted(true);
    expect(r.track.enabled).toBe(false);
    adapter.setMuted(false);
    expect(r.track.enabled).toBe(true);
  });

  test("interrupting cancels the reply and clears the audio", async () => {
    const { adapter, r, events } = await open();

    adapter.interrupt();

    expect(r.peer.channels[0]?.sent).toEqual([
      { type: "response.cancel" },
      { type: "output_audio_buffer.clear" },
    ]);
    expect(events).toEqual([{ type: "listening" }]);
  });

  test("typed text goes as a user message and asks for a reply", async () => {
    const { adapter, r, events } = await open();

    adapter.sendText("  from Indore to Goa  ");

    expect(r.peer.channels[0]?.sent).toEqual([
      {
        type: "conversation.item.create",
        item: { type: "message", role: "user", content: [{ type: "input_text", text: "from Indore to Goa" }] },
      },
      { type: "response.create" },
    ]);
    expect(events[0]).toEqual({ type: "transcript", speaker: "user", text: "from Indore to Goa", source: "typed" });
  });

  test("blank text sends nothing", async () => {
    const { adapter, r } = await open();

    adapter.sendText("   ");

    expect(r.peer.channels[0]?.sent).toEqual([]);
  });

  test("messages from OpenAI become interface events", async () => {
    const { r, events } = await open();
    const channel = r.peer.channels[0] as FakeChannel;
    const deliver = (message: unknown) => channel.onmessage?.({ data: JSON.stringify(message) });

    deliver({ type: "input_audio_buffer.speech_started" });
    deliver({ type: "conversation.item.input_audio_transcription.completed", transcript: " hello " });
    deliver({ type: "response.output_audio_transcript.delta", delta: "Hi" });
    deliver({ type: "response.output_audio_transcript.done", transcript: "Hi there" });
    deliver({ type: "response.done" });

    expect(events).toEqual([
      { type: "listening" },
      { type: "transcript", speaker: "user", text: "hello", source: "voice" },
      { type: "speaking" },
      { type: "transcript", speaker: "assistant", text: "Hi there", source: "assistant" },
      { type: "listening" },
    ]);
  });

  test("the end of speech alone does not show thinking; the reply starting does", async () => {
    const { r, events } = await open();
    const channel = r.peer.channels[0] as FakeChannel;
    const deliver = (message: unknown) => channel.onmessage?.({ data: JSON.stringify(message) });

    deliver({ type: "input_audio_buffer.speech_stopped" });
    expect(events).toEqual([]);
    deliver({ type: "response.created" });
    expect(events).toEqual([{ type: "thinking" }]);
  });

  test("a reply the person talks over is dropped, and the next reply is shown", async () => {
    const { r, events } = await open();
    const channel = r.peer.channels[0] as FakeChannel;
    const deliver = (message: unknown) => channel.onmessage?.({ data: JSON.stringify(message) });

    deliver({ type: "response.created" });
    deliver({ type: "input_audio_buffer.speech_started" });
    deliver({ type: "response.output_audio_transcript.delta", delta: "Sure" });
    deliver({ type: "response.output_audio_transcript.done", transcript: "Sure, which" });
    deliver({ type: "response.done" });
    events.length = 0;
    deliver({ type: "response.created" });
    deliver({ type: "response.output_audio_transcript.done", transcript: "Which day?" });

    expect(events).toEqual([
      { type: "thinking" },
      { type: "transcript", speaker: "assistant", text: "Which day?", source: "assistant" },
    ]);
  });

  test("typed text during a running reply waits and then asks once", async () => {
    const { adapter, r } = await open();
    const channel = r.peer.channels[0] as FakeChannel;
    const deliver = (message: unknown) => channel.onmessage?.({ data: JSON.stringify(message) });

    deliver({ type: "response.created" });
    adapter.sendText("to Goa");
    expect(channel.sent.filter((m) => (m as { type: string }).type === "response.create")).toEqual([]);
    deliver({ type: "response.done" });
    deliver({ type: "response.done" });

    expect(channel.sent.filter((m) => (m as { type: string }).type === "response.create")).toEqual([
      { type: "response.create" },
    ]);
  });

  test("the session ends at the server's time limit and releases everything", async () => {
    const { r, events } = await open();

    expect(r.timers).toHaveLength(1);
    expect(r.timers[0]?.ms).toBe(600_000);
    r.timers[0]?.callback();

    expect(events).toEqual([
      { type: "error", code: "session_expired", message: "The voice session has ended. Start a new one." },
    ]);
    expect(r.peer.closed).toBe(true);
    expect(r.track.stopped).toBe(true);
  });

  test("a dropped connection is reported once", async () => {
    const { r, events } = await open();

    r.peer.connectionState = "failed";
    r.peer.onconnectionstatechange?.();

    expect(events).toEqual([{ type: "error", code: "connection", message: "Lost the voice connection." }]);
  });
});

describe("closing", () => {
  test("disconnecting releases the microphone, the connection and the audio, and ends the session", async () => {
    const r = rig();
    const api = fakeApi();
    const adapter = createRealtimeAdapter({ api, env: r.env });
    await adapter.connect({ microphone: true }, () => undefined);

    adapter.disconnect();

    expect(r.track.stopped).toBe(true);
    expect(r.peer.closed).toBe(true);
    expect(r.peer.channels[0]?.closed).toBe(true);
    expect(r.audio.paused).toBe(true);
    expect(api.ended).toEqual([SESSION]);
  });

  test("disconnecting twice, or before connecting, is safe", async () => {
    const api = fakeApi();
    const adapter = createRealtimeAdapter({ api, env: rig().env });

    adapter.disconnect();
    await adapter.connect({ microphone: false }, () => undefined);
    adapter.disconnect();
    adapter.disconnect();

    expect(api.ended).toEqual([SESSION]);
  });
});

describe("reading messages from OpenAI", () => {
  test.each([
    [undefined],
    [42],
    ["not json"],
    ["{}"],
    [JSON.stringify({ type: "something.new.we.do.not.know" })],
    [JSON.stringify({ type: "response.output_audio_transcript.done", transcript: "  " })],
    [JSON.stringify({ type: "conversation.item.input_audio_transcription.completed" })],
  ])("%j gives no event", (raw) => {
    expect(eventFromMessage(raw)).toBeNull();
  });

  test("an error message becomes a short generic one and never repeats the provider's text", () => {
    const event = eventFromMessage(JSON.stringify({ type: "error", error: { message: "key sk-leak is bad" } }));

    expect(event).toEqual({ type: "error", code: "connection", message: "The voice service reported a problem." });
  });

  test("the older transcript event names still work", () => {
    expect(eventFromMessage(JSON.stringify({ type: "response.audio_transcript.done", transcript: "ok" }))).toEqual({
      type: "transcript",
      speaker: "assistant",
      text: "ok",
      source: "assistant",
    });
  });
});
