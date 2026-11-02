import { useCallback, useEffect, useRef, useState } from "react";

import {
  PlanningApiError,
  chooseOptions,
  createTrip,
  getRun,
  isWorking,
  startRun,
  type PlanningRun,
  type Selection,
} from "../../api/planning";
import type { TripRequest } from "../../contracts/types";
import { stayNights } from "../../demo/demoData";
import { parseRooms } from "../../lib/rooms";

const POLL_MS = 700;

/**
 * Where the conversation's planning journey is:
 * - `idle`: nothing started.
 * - `awaiting-rooms`: the assistant asked how many rooms; the next answer is read as that.
 * - `starting`: the trip and the run are being created.
 * - `active`: a run exists; what to show depends on the run's own status.
 * - `stopped`: the reader stopped waiting.
 * - `failed`: the run could not be started or read.
 */
export type PlanningStage = "idle" | "awaiting-rooms" | "starting" | "active" | "stopped" | "failed";

const FINISHED: readonly string[] = ["completed", "failed", "stopped_limit"];

function errorText(error: unknown): string {
  if (error instanceof PlanningApiError) {
    if (error.status === null) {
      return "The planning server could not be reached. Is the backend running with the planning API switched on?";
    }
    return error.detail ?? `The planning server refused the request (HTTP ${error.status}).`;
  }
  return "Something went wrong while talking to the planning server.";
}

interface Options {
  /** The trip the chat has collected and read back, if any. */
  request: TripRequest | null;
  /** Adds a line to the conversation. These are the page's own words, not the server's. */
  say: (from: "you" | "assistant", text: string) => void;
}

/**
 * Connects the conversation to the existing planning workflow, using the same client as the
 * development panel. It starts a run only when the reader asks for it, reads the answers the
 * server gives, and hands each pause (a question, a choice) and the result to the screen.
 *
 * It cannot book, approve or pay: the approval step is the existing component, which acts only when
 * the reader presses its button. Nothing here calls those endpoints.
 */
export function usePlanningRun({ request, say }: Options) {
  const [stage, setStage] = useState<PlanningStage>("idle");
  const [run, setRun] = useState<PlanningRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plannedKey, setPlannedKey] = useState<string | null>(null);
  const requestRef = useRef<TripRequest | null>(null);
  const controller = useRef<AbortController | null>(null);
  const announced = useRef(new Set<string>());
  const sayRef = useRef(say);
  const live = useRef(true);

  useEffect(() => {
    sayRef.current = say;
  }, [say]);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      controller.current?.abort();
    };
  }, []);

  const tell = useCallback((from: "you" | "assistant", text: string) => sayRef.current(from, text), []);

  const finished = stage === "active" && run !== null && FINISHED.includes(run.status);
  const busy = stage === "awaiting-rooms" || stage === "starting" || (stage === "active" && !finished);

  const launch = useCallback(
    async (trip: TripRequest, rooms: number | null) => {
      controller.current?.abort();
      const mine = new AbortController();
      controller.current = mine;
      setStage("starting");
      setError(null);
      setRun(null);
      try {
        const tripId = await createTrip(`${trip.origin.name} to ${trip.destination.name}`, trip, rooms, mine.signal);
        const started = await startRun(tripId, mine.signal);
        if (!live.current || mine.signal.aborted) {
          return;
        }
        setRun(started);
        setStage("active");
        tell("assistant", "I'm researching transport, hotels and weather for you now.");
      } catch (failure) {
        if (!live.current || mine.signal.aborted) {
          return;
        }
        setError(errorText(failure));
        setStage("failed");
      }
    },
    [tell],
  );

  /** The reader asked to plan the trip the chat has collected. */
  const begin = useCallback(() => {
    if (request === null || busy) {
      return; // a plan is already being made: starting another would only waste the run limit
    }
    requestRef.current = request;
    setPlannedKey(JSON.stringify(request));
    announced.current = new Set();
    setRun(null);
    setError(null);
    if (stayNights(request) < 1) {
      // A one-way or same-day trip has no hotel stay (PRD Q13), so no rooms are needed.
      tell("assistant", "This trip has no hotel stay, so I won't ask about rooms. Planning it now.");
      void launch(request, null);
      return;
    }
    setStage("awaiting-rooms");
    tell(
      "assistant",
      "How many rooms do you need? Please give a number from 1 to 9. I don't assume one: hotels are priced per room.",
    );
  }, [busy, launch, request, tell]);

  /** Reads an answer as the number of rooms. Returns false if no question about rooms is open. */
  const answerRooms = useCallback(
    (text: string): boolean => {
      if (stage !== "awaiting-rooms" || requestRef.current === null) {
        return false;
      }
      const rooms = parseRooms(text);
      if (rooms === null) {
        tell("assistant", "I need a number of rooms from 1 to 9, for example “2 rooms”. How many rooms do you need?");
        return true;
      }
      void launch(requestRef.current, rooms);
      return true;
    },
    [launch, stage, tell],
  );

  // While the server works, read the run again shortly.
  useEffect(() => {
    if (stage !== "active" || run === null || !isWorking(run)) {
      return;
    }
    const mine = new AbortController();
    const timer = window.setTimeout(() => {
      getRun(run.runId, mine.signal)
        .then((next) => {
          if (live.current && !mine.signal.aborted) {
            setRun(next);
          }
        })
        .catch((failure: unknown) => {
          if (live.current && !mine.signal.aborted) {
            setError(errorText(failure));
            setStage("failed");
          }
        });
    }, POLL_MS);
    return () => {
      window.clearTimeout(timer);
      mine.abort();
    };
  }, [run, stage]);

  // Say once, in words, each time the run reaches a point the reader should know about.
  useEffect(() => {
    if (stage !== "active" || run === null) {
      return;
    }
    const key = `${run.runId}:${run.status}`;
    if (announced.current.has(key)) {
      return;
    }
    if (run.status === "awaiting_selection") {
      announced.current.add(key);
      tell("assistant", "I found options. Choose one for each leg below, and a hotel if the trip has a stay.");
    } else if (run.status === "awaiting_clarification") {
      announced.current.add(key);
      tell("assistant", "The planner needs a few more details. Please answer below.");
    } else if (run.status === "completed") {
      announced.current.add(key);
      tell("assistant", "Your plan is ready: the estimate, the weather and a draft itinerary are below. Nothing is booked.");
    }
  }, [run, stage, tell]);

  const choose = useCallback(
    async (selection: Selection) => {
      if (run === null) {
        return;
      }
      setError(null);
      try {
        const next = await chooseOptions(run.runId, selection);
        if (live.current) {
          setRun(next);
        }
      } catch (failure) {
        if (live.current) {
          setError(errorText(failure));
        }
      }
    },
    [run],
  );

  /** The run came back from a question the reader answered. */
  const resume = useCallback((next: PlanningRun) => setRun(next), []);

  /** Stop waiting. The server cannot cancel a run, so it may still finish there. Nothing is booked. */
  const stop = useCallback(() => {
    controller.current?.abort();
    setStage("stopped");
    tell("assistant", "I've stopped waiting for the plan. It may still finish in the background; nothing is booked.");
  }, [tell]);

  const key = request === null ? null : JSON.stringify(request);

  return {
    stage,
    run,
    error,
    /** The details changed after the plan was made, so what is shown is for the earlier ones. */
    stale: plannedKey !== null && key !== null && key !== plannedKey,
    awaitingRooms: stage === "awaiting-rooms",
    canStart: request !== null && !busy,
    busy,
    begin,
    answerRooms,
    choose,
    resume,
    stop,
  };
}

export type PlanningRunController = ReturnType<typeof usePlanningRun>;
