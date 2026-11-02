import { useId } from "react";

import { isWorking, type PlanningRun } from "../../api/planning";
import { addMoney } from "../../lib/money";
import { ProvenanceBadge } from "../Badges";
import { MoneyText } from "../MoneyText";
import { ServerBooking } from "../ServerBooking";
import { ServerClarification } from "../ServerClarification";
import { ServerItinerary } from "../ServerItinerary";
import { StatusMessage } from "../StatusMessage";
import { WeatherCard } from "../WeatherCard";
import { RunChoices } from "./RunChoices";
import type { PlanningRunController } from "./usePlanningRun";

function EstimateCard({ run }: { run: PlanningRun }) {
  const titleId = useId();
  const estimate = run.estimate;
  if (estimate === null) {
    return (
      <StatusMessage kind="info" title="No estimate">
        The run finished without a cost estimate.
      </StatusMessage>
    );
  }
  const total = estimate.lines.reduce((sum, line) => addMoney(sum, line.amount), {
    amount_minor: 0,
    currency: estimate.currency,
  });
  return (
    <section className="card" aria-labelledby={titleId}>
      <h3 id={titleId}>
        Cost estimate{" "}
        {estimate.missing_items.length > 0 && <span className="badge badge-incomplete">Incomplete</span>}
      </h3>
      {/* A list, not a table: a description, its source label and its amount reflow on a phone,
          where a three-column table squeezes the description to a few letters per line. */}
      <ul className="estimate-lines" aria-label="Cost lines">
        {estimate.lines.map((line) => (
          <li key={`${line.kind}-${line.description}`}>
            <span className="estimate-text">{line.description}</span>
            <span className="estimate-meta">
              <ProvenanceBadge provenance={line.provenance} />
              <MoneyText money={line.amount} />
            </span>
          </li>
        ))}
        <li className="estimate-total">
          <strong className="estimate-text">Total of the lines shown</strong>
          <span className="estimate-meta">
            <strong>
              <MoneyText money={total} />
            </strong>
          </span>
        </li>
      </ul>
      {estimate.missing_items.length > 0 && (
        <p className="field-hint">Not priced: {estimate.missing_items.join(", ")}.</p>
      )}
    </section>
  );
}

function Results({ run }: { run: PlanningRun }) {
  return (
    <>
      {run.providerIssues.length > 0 && (
        <StatusMessage kind="info" title="Some information could not be found">
          <ul>
            {run.providerIssues.map((issue) => (
              <li key={`${issue.provider}-${issue.message}`}>
                {issue.provider}: {issue.message}
              </li>
            ))}
          </ul>
        </StatusMessage>
      )}
      {run.notes.length > 0 && (
        <ul className="field-hint">
          {run.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <EstimateCard run={run} />
      {run.weather !== null && <WeatherCard weather={run.weather} />}
      {run.itinerary !== null && (
        <ServerItinerary
          key={run.runId}
          tripId={run.tripId}
          initial={run.itinerary}
          warnings={run.itineraryWarnings}
        />
      )}
      <ServerBooking run={run} />
    </>
  );
}

interface RunPanelProps {
  planning: PlanningRunController;
}

/**
 * The planning journey, shown inside the conversation: waiting, a question, the choices, then the
 * estimate, the weather, the draft itinerary and the approval step. It only displays what the
 * existing planning workflow returns, labelled as that data is (MOCK). It can book nothing.
 */
export function RunPanel({ planning }: RunPanelProps) {
  const titleId = useId();
  const { stage, run, error, stale } = planning;
  if (stage === "idle") {
    return null;
  }
  return (
    <section className="run-panel" aria-labelledby={titleId}>
      <h2 id={titleId}>Trip planning</h2>
      <p className="field-hint">
        This uses the planner with sample (MOCK) data from the development server. Nothing is booked.
      </p>

      {stale && (
        <StatusMessage kind="info" title="The trip details changed">
          What is shown is for the earlier details. Choose “Plan this trip” again to refresh it.
        </StatusMessage>
      )}
      {error !== null && (
        <StatusMessage kind="error" title="The planning server did not complete this">
          {error}
        </StatusMessage>
      )}

      {stage === "awaiting-rooms" && (
        <p role="status">Waiting for the number of rooms. Type it in the message box.</p>
      )}
      {stage === "starting" && (
        <StatusMessage kind="loading" title="Starting the plan">
          Creating the trip and asking the planner to research it.
        </StatusMessage>
      )}
      {stage === "stopped" && (
        <StatusMessage kind="info" title="You stopped waiting">
          The planner may still finish in the background. Nothing is booked.
        </StatusMessage>
      )}

      {stage === "active" && run !== null && (
        <>
          {isWorking(run) && (
            <div className="conversation-status">
              <p role="status">
                <span className="thinking-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                Researching transport, hotels and weather…
              </p>
              <button type="button" className="button button-small button-quiet" onClick={planning.stop}>
                Stop
              </button>
            </div>
          )}
          {run.status === "awaiting_clarification" && <ServerClarification run={run} onAnswered={planning.resume} />}
          {run.status === "awaiting_selection" && (
            <>
              {run.weather !== null && <WeatherCard weather={run.weather} />}
              <RunChoices key={run.runId} run={run} onChoose={(selection) => void planning.choose(selection)} />
            </>
          )}
          {run.status === "completed" && <Results run={run} />}
          {(run.status === "failed" || run.status === "stopped_limit") && (
            <StatusMessage kind="error" title="The run did not finish">
              {run.error ?? "The planner stopped this run."}
            </StatusMessage>
          )}
        </>
      )}
    </section>
  );
}
