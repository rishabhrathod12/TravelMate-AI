import { useEffect, useId, useState, type FormEvent } from "react";

import {
  PlanningApiError,
  answerClarification,
  getTripDraft,
  type PlanningRun,
  type TripDraft,
} from "../api/planning";
import { StatusMessage } from "./StatusMessage";

interface ServerClarificationProps {
  run: PlanningRun;
  /** Called with the run the server returns once it has the corrected details. */
  onAnswered: (run: PlanningRun) => void;
}

function failureText(error: unknown): string {
  if (error instanceof PlanningApiError) {
    return error.status === null
      ? "The planning server could not be reached."
      : (error.detail ?? `The planning server refused the request (HTTP ${error.status}).`);
  }
  return "Something went wrong while talking to the planning server.";
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * The server's questions and a small form for the details it may be missing. It starts from the
 * trip's draft as the server holds it and sends back the whole draft with the traveller's changes.
 * It guesses nothing: a blank field is sent as not given.
 */
export function ServerClarification({ run, onAnswered }: ServerClarificationProps) {
  const [draft, setDraft] = useState<TripDraft | null>(null);
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departure, setDeparture] = useState("");
  const [returning, setReturning] = useState("");
  const [travellers, setTravellers] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const baseId = useId();

  useEffect(() => {
    const controller = new AbortController();
    getTripDraft(run.tripId, controller.signal).then(
      (loaded) => {
        setDraft(loaded);
        setOrigin(textOf(loaded.origin));
        setDestination(textOf(loaded.destination));
        setDeparture(textOf(loaded.departure_date));
        setReturning(textOf(loaded.return_date));
        setTravellers(typeof loaded.traveller_count === "number" ? String(loaded.traveller_count) : "");
      },
      (failure: unknown) => {
        if (!controller.signal.aborted) {
          setError(failureText(failure));
        }
      },
    );
    return () => controller.abort();
  }, [run.tripId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (draft === null) {
      return;
    }
    const count = Number(travellers);
    setBusy(true);
    setError(null);
    try {
      const answered = await answerClarification(run.runId, {
        ...draft,
        origin: origin.trim() === "" ? null : origin.trim(),
        destination: destination.trim() === "" ? null : destination.trim(),
        departure_date: departure === "" ? null : departure,
        return_date: returning === "" ? null : returning,
        traveller_count: Number.isInteger(count) && count >= 1 ? count : null,
      });
      onAnswered(answered);
    } catch (failure) {
      setError(failureText(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={`${baseId}-title`}>
      <h3 id={`${baseId}-title`}>The server needs more detail</h3>
      {run.questions.length > 0 ? (
        <ul>
          {run.questions.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      ) : (
        <p>The server asked for details this screen could not read. Check the trip below.</p>
      )}
      <form onSubmit={(event) => void submit(event)}>
        <p>
          <label htmlFor={`${baseId}-o`}>From</label>{" "}
          <input id={`${baseId}-o`} type="text" value={origin} onChange={(e) => setOrigin(e.target.value)} />
        </p>
        <p>
          <label htmlFor={`${baseId}-d`}>To</label>{" "}
          <input id={`${baseId}-d`} type="text" value={destination} onChange={(e) => setDestination(e.target.value)} />
        </p>
        <p>
          <label htmlFor={`${baseId}-dep`}>Departure date</label>{" "}
          <input id={`${baseId}-dep`} type="date" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </p>
        <p>
          <label htmlFor={`${baseId}-ret`}>Return date (leave blank for one way)</label>{" "}
          <input id={`${baseId}-ret`} type="date" value={returning} onChange={(e) => setReturning(e.target.value)} />
        </p>
        <p>
          <label htmlFor={`${baseId}-n`}>Travellers</label>{" "}
          <input
            id={`${baseId}-n`}
            type="number"
            min={1}
            max={9}
            inputMode="numeric"
            value={travellers}
            onChange={(e) => setTravellers(e.target.value)}
          />
        </p>
        {error !== null && (
          <StatusMessage kind="error" title="The answer was not accepted">
            {error}
          </StatusMessage>
        )}
        <p>
          <button type="submit" className="button button-primary" disabled={busy || draft === null}>
            Send these details
          </button>
        </p>
      </form>
    </section>
  );
}
