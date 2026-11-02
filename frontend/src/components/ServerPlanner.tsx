import { useEffect, useRef, useState } from "react";

import {
  PlanningApiError,
  chooseOptions,
  createTrip,
  getRun,
  isWorking,
  startRun,
  type PlanningRun,
  type Selection,
} from "../api/planning";
import type { HotelOption, Money, TransportOption, TripRequest } from "../contracts/types";
import { formatUtcDateTime } from "../lib/dates";
import { addMoney } from "../lib/money";
import { AvailabilityBadge, ProvenanceBadge } from "./Badges";
import { MoneyText } from "./MoneyText";
import { StatusMessage } from "./StatusMessage";

const POLL_MS = 700;

type Phase = "idle" | "starting" | "run";

function errorText(error: unknown): string {
  if (error instanceof PlanningApiError) {
    if (error.status === null) {
      return "The planning server could not be reached. Is the backend running with the API switched on?";
    }
    return error.detail ?? `The planning server refused the request (HTTP ${error.status}).`;
  }
  return "Something went wrong while talking to the planning server.";
}

interface ChoiceListProps<T extends { id: string }> {
  legend: string;
  name: string;
  options: T[];
  allowed: string[];
  chosen: string | null;
  onChoose: (id: string) => void;
  describe: (option: T) => string;
  price: (option: T) => Money | null;
}

function ChoiceList<T extends TransportOption | HotelOption>({
  legend,
  name,
  options,
  allowed,
  chosen,
  onChoose,
  describe,
  price,
}: ChoiceListProps<T>) {
  const shown = options.filter((option) => allowed.includes(option.id));
  if (shown.length === 0) {
    return null;
  }
  return (
    <fieldset className="card">
      <legend>{legend}</legend>
      {shown.map((option) => {
        const amount = price(option);
        return (
          <label key={option.id} className="choice-row">
            <input
              type="radio"
              name={name}
              checked={chosen === option.id}
              onChange={() => onChoose(option.id)}
            />{" "}
            <span>{describe(option)}</span>{" "}
            {amount !== null ? <MoneyText money={amount} /> : <span>No price</span>}{" "}
            <ProvenanceBadge provenance={option.source.provenance} />{" "}
            <AvailabilityBadge availability={option.availability} />
            <span className="field-hint">
              {" "}
              Retrieved {formatUtcDateTime(option.source.retrieved_at)}
              {option.source.provenance === "MOCK" ? " (fictional demo timestamp)" : ""}
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}

interface ServerPlannerProps {
  request: TripRequest;
}

/**
 * Plans the trip with the real planning API: creates the trip, starts a run, shows the options the
 * server found (each with its provenance), sends the traveller's choice and shows the priced
 * estimate. Development builds only (no authentication exists yet, PRD Q4). Nothing is booked.
 * The parent gives it a `key` made from the request, so a new request starts a fresh plan.
 */
export function ServerPlanner({ request }: ServerPlannerProps) {
  const [rooms, setRooms] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [run, setRun] = useState<PlanningRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>({
    transportId: null,
    returnTransportId: null,
    hotelId: null,
  });
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  // While the server works, read the run again shortly.
  useEffect(() => {
    if (run === null || !isWorking(run)) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      getRun(run.runId, controller.signal)
        .then((next) => {
          if (live.current) {
            setRun(next);
          }
        })
        .catch((failure: unknown) => {
          if (live.current && !controller.signal.aborted) {
            setError(errorText(failure));
          }
        });
    }, POLL_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [run]);

  const roomCount = Number(rooms);
  const roomsValid = Number.isInteger(roomCount) && roomCount >= 1 && roomCount <= 9;

  async function start() {
    setError(null);
    setPhase("starting");
    try {
      const title = `${request.origin.name} to ${request.destination.name}`;
      const tripId = await createTrip(title, request, roomCount);
      const started = await startRun(tripId);
      if (live.current) {
        setRun(started);
        setPhase("run");
      }
    } catch (failure) {
      if (live.current) {
        setError(errorText(failure));
        setPhase("idle");
      }
    }
  }

  async function submitChoice() {
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
  }

  const choices = run?.choices ?? null;
  const research = run?.research ?? null;
  const needsReturn = (choices?.returnTransport.length ?? 0) > 0;
  const needsHotel = (choices?.hotels.length ?? 0) > 0;
  const ready =
    selection.transportId !== null &&
    (!needsReturn || selection.returnTransportId !== null) &&
    (!needsHotel || selection.hotelId !== null);
  const estimate = run?.estimate ?? null;
  const total =
    estimate === null
      ? null
      : estimate.lines.reduce(
          (sum, line) => addMoney(sum, line.amount),
          { amount_minor: 0, currency: estimate.currency },
        );

  return (
    <section className="card" aria-labelledby="server-planner-title">
      <h2 id="server-planner-title">Plan with the server (development)</h2>
      <p className="field-hint">
        Sends this trip to the planning API on your own machine. Options and prices come from the
        server and keep the label it gives them; MOCK means sample data. Nothing is booked.
      </p>

      {phase === "idle" && (
        <p>
          <label>
            Rooms needed{" "}
            <input
              type="number"
              min={1}
              max={9}
              inputMode="numeric"
              value={rooms}
              aria-describedby="rooms-hint"
              onChange={(event) => setRooms(event.target.value)}
            />
          </label>{" "}
          <button type="button" className="button" disabled={!roomsValid} onClick={() => void start()}>
            Plan with the server
          </button>
          <span id="rooms-hint" className="field-hint">
            {" "}
            There is no default number of rooms: say how many your party needs (1 to 9).
          </span>
        </p>
      )}

      {phase === "starting" && (
        <StatusMessage kind="loading" title="Starting the plan">
          Creating the trip and asking the server to research it.
        </StatusMessage>
      )}

      {error !== null && (
        <StatusMessage kind="error" title="The planning server did not complete this">
          {error}
        </StatusMessage>
      )}

      {run !== null && isWorking(run) && error === null && (
        <StatusMessage kind="loading" title="The server is researching">
          Looking at transport and hotels. This page checks again in a moment.
        </StatusMessage>
      )}

      {run !== null && run.status === "awaiting_clarification" && (
        <StatusMessage kind="info" title="The server needs more detail">
          The server asked a question this screen does not handle yet. Go back to the chat or the
          form and complete the trip details.
        </StatusMessage>
      )}

      {run !== null && (run.status === "failed" || run.status === "stopped_limit") && (
        <StatusMessage kind="error" title="The run did not finish">
          {run.error ?? "The server stopped this run."}
        </StatusMessage>
      )}

      {run !== null && run.status === "awaiting_selection" && choices !== null && research !== null && (
        <div>
          <h3>Choose from what the server found</h3>
          <ChoiceList
            legend="Outbound transport"
            name="transport"
            options={research.transport}
            allowed={choices.transport}
            chosen={selection.transportId}
            onChoose={(id) => setSelection({ ...selection, transportId: id })}
            describe={(o) => `${o.mode} ${o.operator_name ?? ""} ${o.service_label ?? ""}`.trim()}
            price={(o) => o.price}
          />
          <ChoiceList
            legend="Return transport"
            name="return-transport"
            options={research.returnTransport}
            allowed={choices.returnTransport}
            chosen={selection.returnTransportId}
            onChoose={(id) => setSelection({ ...selection, returnTransportId: id })}
            describe={(o) => `${o.mode} ${o.operator_name ?? ""} ${o.service_label ?? ""}`.trim()}
            price={(o) => o.price}
          />
          <ChoiceList
            legend="Hotel"
            name="hotel"
            options={research.hotels}
            allowed={choices.hotels}
            chosen={selection.hotelId}
            onChoose={(id) => setSelection({ ...selection, hotelId: id })}
            describe={(o) => `${o.name} (per room per night)`}
            price={(o) => o.nightly_rate}
          />
          <p>
            <button type="button" className="button" disabled={!ready} onClick={() => void submitChoice()}>
              Use these choices
            </button>
          </p>
        </div>
      )}

      {run !== null && run.status === "completed" && (
        <div>
          <h3>Estimate from the server</h3>
          {estimate === null || total === null ? (
            <StatusMessage kind="info" title="No estimate">
              The run finished without a cost estimate.
            </StatusMessage>
          ) : (
            <table className="cost-table">
              <caption>
                Cost estimate{" "}
                {estimate.missing_items.length > 0 && (
                  <span className="badge badge-incomplete">Incomplete</span>
                )}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Source</th>
                  <th scope="col" className="numeric">
                    Amount
                  </th>
                </tr>
              </thead>
              <tbody>
                {estimate.lines.map((line) => (
                  <tr key={`${line.kind}-${line.description}`}>
                    <th scope="row">{line.description}</th>
                    <td>
                      <ProvenanceBadge provenance={line.provenance} />
                    </td>
                    <td className="numeric">
                      <MoneyText money={line.amount} />
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row" colSpan={2}>
                    Total of the lines shown
                  </th>
                  <td className="numeric">
                    <MoneyText money={total} />
                  </td>
                </tr>
              </tfoot>
            </table>
          )}
          {estimate !== null && estimate.missing_items.length > 0 && (
            <p className="field-hint">Not priced: {estimate.missing_items.join(", ")}.</p>
          )}
        </div>
      )}
    </section>
  );
}
