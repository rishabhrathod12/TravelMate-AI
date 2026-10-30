import { useCallback, useEffect, useId, useState } from "react";

import { ChatApiError, requestPlan } from "../api/chat";
import type { ItineraryRequest, PlanResponse, SuggestionLabel } from "../contracts/types";
import { addDays, formatDay } from "../lib/dates";

interface PlanSectionProps {
  request: ItineraryRequest;
  /** Replaceable in tests. */
  load?: typeof requestPlan;
}

type Outcome = { phase: "failed"; message: string } | { phase: "ready"; response: PlanResponse };
type State = { phase: "loading" } | Outcome;

const BANNER: Record<SuggestionLabel, string> = {
  SCRIPTED_SAMPLE: "Scripted sample · not written by a language model · not verified",
  AI_SUGGESTION: "AI suggestion · not verified",
};

const LINE_LABEL: Record<SuggestionLabel, string> = {
  SCRIPTED_SAMPLE: "Scripted sample",
  AI_SUGGESTION: "AI suggestion, not verified",
};

function failureText(error: unknown): string {
  if (error instanceof ChatApiError) {
    if (error.status === null) {
      return "The server could not be reached. Is the backend running?";
    }
    return error.detail ?? `The server answered HTTP ${error.status}.`;
  }
  return "Something went wrong. Please try again.";
}

/**
 * The plan for an itinerary request, as the server wrote it. Where it came from is shown from the
 * server's own `source`, on a banner and on every line: a scripted sample is never presented as a
 * model's work, and a model's suggestion is never presented as fact. Calendar dates are worked out
 * here from the start date. If the server cannot answer, this says so and shows no plan: it never
 * makes one up locally.
 */
export function PlanSection({ request, load = requestPlan }: PlanSectionProps) {
  // The answer is stored with the request it belongs to, so "loading" is simply "no answer for the
  // current request yet". Nothing is set synchronously inside the effect.
  const [answer, setAnswer] = useState<{ id: string; outcome: Outcome } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const headingId = useId();

  const key = JSON.stringify(request);
  const id = `${attempt}:${key}`;
  const retry = useCallback(() => setAttempt((count) => count + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    load(JSON.parse(key) as ItineraryRequest, controller.signal).then(
      (response) => {
        if (!controller.signal.aborted) {
          setAnswer({ id, outcome: { phase: "ready", response } });
        }
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setAnswer({ id, outcome: { phase: "failed", message: failureText(error) } });
        }
      },
    );
    return () => controller.abort();
  }, [id, key, load]);

  const state: State = answer !== null && answer.id === id ? answer.outcome : { phase: "loading" };

  const title = `${request.days}-day plan for ${request.destination.name}`;

  if (state.phase === "loading") {
    return (
      <section className="card sample-plan" aria-labelledby={headingId} aria-busy="true">
        <h2 id={headingId}>{title}</h2>
        <p role="status">Writing your plan…</p>
      </section>
    );
  }

  if (state.phase === "failed") {
    return (
      <section className="card sample-plan" aria-labelledby={headingId}>
        <h2 id={headingId}>{title}</h2>
        <p role="alert" className="chat-error">
          The plan could not be written. {state.message}
        </p>
        <button type="button" className="button" onClick={retry}>
          Try again
        </button>
      </section>
    );
  }

  const { source, notice, plan } = state.response;
  return (
    <section className="card sample-plan" aria-labelledby={headingId}>
      <h2 id={headingId}>{title}</h2>
      <p className="badge badge-mock">{BANNER[source]}</p>
      <p className="field-hint">
        {notice} Starting {formatDay(request.start_date)}
        {request.travellers !== null
          ? ` · ${request.travellers} ${request.travellers === 1 ? "traveller" : "travellers"}`
          : ""}
        . Nothing here can be booked.
      </p>
      <ol className="itinerary">
        {plan.days.map((day) => {
          const dayId = `${headingId}-day-${day.day_number}`;
          return (
            <li key={day.day_number}>
              <section aria-labelledby={dayId}>
                <h3 id={dayId}>
                  Day {day.day_number}
                  <span className="day-date">
                    {" "}
                    · {formatDay(addDays(request.start_date, day.day_number - 1))}
                  </span>
                </h3>
                <ul className="activity-list">
                  {day.items.map((item, index) => (
                    <li key={`${index}-${item.title}`}>
                      <p className="activity-title">{item.title}</p>
                      {item.description !== null && (
                        <p className="activity-text">{item.description}</p>
                      )}
                      <p className="field-hint">{LINE_LABEL[source]}</p>
                    </li>
                  ))}
                </ul>
              </section>
            </li>
          );
        })}
      </ol>
      {plan.notes !== null && <p className="field-hint">{plan.notes}</p>}
    </section>
  );
}
