import { afterEach, describe, expect, test, vi } from "vitest";

import { ChatApiError, sendChatTurn } from "./chat";

const REQUEST = {
  trip_type: "ONE_WAY",
  origin: { name: "Indore" },
  destination: { name: "Goa" },
  departure_date: "2026-12-12",
  return_date: null,
  travellers: [{ age: null }],
  preferences: null,
};

const GOOD = {
  status: "READY_FOR_REVIEW",
  reply: "Here is what I have.",
  draft: { origin: "Indore" },
  trip_request: REQUEST,
  changes: [],
  rejections: [],
  model: { kind: "DEV_STAND_IN", notice: "Development stand-in." },
};

function answer(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("sendChatTurn", () => {
  test("posts the message and the draft, and returns the turn", async () => {
    const fetchMock = answer(GOOD);

    const turn = await sendChatTurn("Indore to Goa", { origin: "Indore" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/chat/turns");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      message: "Indore to Goa",
      draft: { origin: "Indore" },
    });
    expect(turn.status).toBe("READY_FOR_REVIEW");
    expect(turn.tripRequest?.destination.name).toBe("Goa");
    expect(turn.modelKind).toBe("DEV_STAND_IN");
  });

  test("sends a null draft on the first turn", async () => {
    const fetchMock = answer({ ...GOOD, status: "NEEDS_INFO", trip_request: null });

    await sendChatTurn("hi", null);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((JSON.parse(init.body as string) as { draft: unknown }).draft).toBeNull();
  });

  test("a date waiting for a yes is a normal answer, and the draft carries it back", async () => {
    const waiting = { pending_date: { phrase: "this weekend", value: "2026-11-07" } };
    answer({ ...GOOD, status: "CONFIRM_DATES", trip_request: null, draft: waiting });

    const turn = await sendChatTurn("Goa this weekend", null);

    expect(turn.status).toBe("CONFIRM_DATES");
    expect(turn.tripRequest).toBeNull();
    expect(turn.draft).toEqual(waiting);
  });

  test("an itinerary request is read, and a malformed one is refused", async () => {
    const itinerary = {
      destination: { name: "Goa" },
      start_date: "2026-11-07",
      days: 5,
      travellers: null,
      preferences: null,
    };
    answer({ ...GOOD, trip_request: null, itinerary_request: itinerary });
    const turn = await sendChatTurn("plan 5 days in Goa", null);
    expect(turn.itineraryRequest?.days).toBe(5);
    expect(turn.tripRequest).toBeNull();

    answer({ ...GOOD, trip_request: null, itinerary_request: { ...itinerary, days: 0 } });
    await expect(sendChatTurn("x", null)).rejects.toBeInstanceOf(ChatApiError);
  });

  test("an answer of the wrong shape is refused", async () => {
    answer({ ...GOOD, status: "SOMETHING_ELSE" });

    await expect(sendChatTurn("hi", null)).rejects.toBeInstanceOf(ChatApiError);
  });

  test("a trip request with no travellers is refused", async () => {
    answer({ ...GOOD, trip_request: { ...REQUEST, travellers: [] } });

    await expect(sendChatTurn("hi", null)).rejects.toBeInstanceOf(ChatApiError);
  });

  test("a problem answer carries the server's detail", async () => {
    answer({ title: "Draft too large", detail: "A value in the draft is longer than allowed." }, 422);

    const error = await sendChatTurn("hi", null).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ChatApiError);
    expect((error as ChatApiError).status).toBe(422);
    expect((error as ChatApiError).detail).toBe("A value in the draft is longer than allowed.");
  });

  test("an unreachable server gives a null status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));

    const error = await sendChatTurn("hi", null).catch((caught: unknown) => caught);

    expect((error as ChatApiError).status).toBeNull();
  });
});
