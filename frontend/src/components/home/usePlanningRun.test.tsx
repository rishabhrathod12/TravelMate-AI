import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { TripRequest } from "../../contracts/types";
import {
  AWAITING_SELECTION,
  COMPLETED,
  ONE_WAY,
  ROUND_TRIP,
  RUNNING,
  json,
  stubPlanningServer,
} from "../../test/planningFixtures";
import { usePlanningRun } from "./usePlanningRun";

afterEach(() => vi.unstubAllGlobals());

const START = { "POST /api/v1/trips": () => json({ id: "t1" }, 201), "POST /api/v1/trips/t1/runs": () => json(RUNNING, 202) };

function setup(request: TripRequest | null = ROUND_TRIP) {
  const say = vi.fn<(from: "you" | "assistant", text: string) => void>();
  const hook = renderHook(({ trip }) => usePlanningRun({ request: trip, say }), { initialProps: { trip: request } });
  return { ...hook, say };
}

const said = (say: ReturnType<typeof setup>["say"]) => say.mock.calls.map(([, text]) => text);

describe("asking for rooms", () => {
  test("a trip with a hotel stay asks how many rooms, and starts nothing until it is answered", () => {
    const server = stubPlanningServer({});
    const { result, say } = setup();

    act(() => result.current.begin());

    expect(result.current.stage).toBe("awaiting-rooms");
    expect(result.current.awaitingRooms).toBe(true);
    expect(said(say).join(" ")).toMatch(/How many rooms/);
    expect(server.spy).not.toHaveBeenCalled();
  });

  test("a one-way trip has no hotel stay, so it does not ask and plans with no rooms", async () => {
    const server = stubPlanningServer(START);
    const { result, say } = setup(ONE_WAY);

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.stage).toBe("active"));
    expect(said(say).join(" ")).toMatch(/no hotel stay/);
    expect(said(say).join(" ")).not.toMatch(/How many rooms/);
    expect((server.bodyOf("POST /api/v1/trips") as { rooms: number | null }).rooms).toBeNull();
  });

  test("an answer that is not a number of rooms is asked again, and nothing is sent", () => {
    const server = stubPlanningServer({});
    const { result, say } = setup();
    act(() => result.current.begin());

    let handled = false;
    act(() => {
      handled = result.current.answerRooms("banana");
    });

    expect(handled).toBe(true); // the message was consumed as an answer, not sent on as a chat turn
    expect(result.current.stage).toBe("awaiting-rooms");
    expect(said(say).at(-1)).toMatch(/number of rooms from 1 to 9/);
    expect(server.spy).not.toHaveBeenCalled();
  });

  test.each(["0", "10", "4 people", "I don't know"])("%j is never turned into a number of rooms", (text) => {
    const server = stubPlanningServer({});
    const { result } = setup();
    act(() => result.current.begin());

    act(() => {
      result.current.answerRooms(text);
    });

    expect(result.current.stage).toBe("awaiting-rooms");
    expect(server.spy).not.toHaveBeenCalled();
  });

  test("a clear answer starts the plan with exactly that many rooms", async () => {
    const server = stubPlanningServer(START);
    const { result } = setup();
    act(() => result.current.begin());

    act(() => {
      result.current.answerRooms("two rooms");
    });

    await waitFor(() => expect(result.current.stage).toBe("active"));
    const body = server.bodyOf("POST /api/v1/trips") as { rooms: number; title: string; draft: Record<string, unknown> };
    expect(body.rooms).toBe(2);
    expect(body.title).toBe("Indore to Goa");
    expect(body.draft).toMatchObject({ origin: "Indore", destination: "Goa", traveller_count: 2 });
  });

  test("when no question about rooms is open, a message is not taken as an answer", () => {
    stubPlanningServer({});
    const { result } = setup();

    expect(result.current.answerRooms("2")).toBe(false);
  });
});

describe("the run", () => {
  test("is announced once at each point the reader should know about, and never books", async () => {
    const server = stubPlanningServer({
      ...START,
      "GET /api/v1/runs/r1": () => json(AWAITING_SELECTION),
      "POST /api/v1/runs/r1/selections": () => json(COMPLETED, 202),
    });
    const { result, say } = setup(ONE_WAY);
    act(() => result.current.begin());

    await waitFor(() => expect(result.current.run?.status).toBe("awaiting_selection"), { timeout: 4000 });
    expect(said(say).filter((text) => /I found options/.test(text))).toHaveLength(1);

    await act(async () => {
      await result.current.choose({ transportId: "a", returnTransportId: null, hotelId: null });
    });

    await waitFor(() => expect(result.current.run?.status).toBe("completed"));
    expect(said(say).filter((text) => /Your plan is ready/.test(text))).toHaveLength(1);
    expect(result.current.busy).toBe(false);
    expect(result.current.canStart).toBe(true);
    expect(server.bodyOf("POST /api/v1/runs/r1/selections")).toEqual({
      transport_id: "a",
      return_transport_id: null,
      hotel_id: null,
    });
    // The controller never reaches the booking path: that is only the reader's own button.
    expect(server.keys().some((key) => /booking-intents|approvals|execute/.test(key))).toBe(false);
  }, 15000);

  test("a second request to plan while one is running starts nothing new", async () => {
    const server = stubPlanningServer({ ...START, "GET /api/v1/runs/r1": () => json(RUNNING) });
    const { result } = setup(ONE_WAY);
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.stage).toBe("active"));

    expect(result.current.canStart).toBe(false);
    act(() => result.current.begin());

    expect(server.keys().filter((key) => key === "POST /api/v1/trips")).toHaveLength(1);
  });

  test("a server that refuses shows its own words, and the reader can try again", async () => {
    stubPlanningServer({
      "POST /api/v1/trips": () => json({ title: "Too many runs", detail: "You have started too many plans this hour." }, 429),
    });
    const { result } = setup(ONE_WAY);

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.stage).toBe("failed"));
    expect(result.current.error).toBe("You have started too many plans this hour.");
    expect(result.current.canStart).toBe(true);
  });

  test("a server that cannot be reached is reported plainly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const { result } = setup(ONE_WAY);

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.stage).toBe("failed"));
    expect(result.current.error).toMatch(/could not be reached/);
  });

  test("stopping ends the waiting, says that nothing is booked, and allows a new plan", async () => {
    stubPlanningServer({ ...START, "GET /api/v1/runs/r1": () => json(RUNNING) });
    const { result, say } = setup(ONE_WAY);
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.stage).toBe("active"));

    act(() => result.current.stop());

    expect(result.current.stage).toBe("stopped");
    expect(said(say).at(-1)).toMatch(/nothing is booked/);
    expect(result.current.canStart).toBe(true);
  });
});

describe("when the trip changes", () => {
  test("results for earlier details are marked as such, and nothing is wiped by a message that is not a trip", async () => {
    stubPlanningServer({ ...START, "GET /api/v1/runs/r1": () => json(COMPLETED) });
    const { result, rerender } = setup(ONE_WAY);
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.run?.status).toBe("completed"), { timeout: 4000 });
    expect(result.current.stale).toBe(false);

    // A chat turn that is not a ready trip leaves no request: the results stay, not stale.
    rerender({ trip: null });
    expect(result.current.stale).toBe(false);
    expect(result.current.run?.status).toBe("completed");

    // A different ready trip: the shown results are for the earlier one.
    rerender({ trip: { ...ONE_WAY, destination: { name: "Mumbai" } } });
    expect(result.current.stale).toBe(true);
    expect(result.current.canStart).toBe(true);
  }, 15000);
});
