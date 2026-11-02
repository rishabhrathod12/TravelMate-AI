import { useState } from "react";

import {
  approveIntent,
  createIntent,
  getIntent,
  type BookingIntent,
  type QuoteCategory,
} from "../api/booking";
import { PlanningApiError, type PlanningRun } from "../api/planning";
import type { HotelOption, PriceBasis, TransportOption } from "../contracts/types";
import { formatUtcDateTime } from "../lib/dates";
import { AvailabilityBadge } from "./Badges";
import { MoneyText } from "./MoneyText";
import { SourceLine } from "./SourceLine";
import { StatusMessage } from "./StatusMessage";

const BASIS_TEXT: Record<PriceBasis, string> = {
  PER_TRAVELLER: "per traveller",
  PER_ROOM_NIGHT: "per room per night",
  PER_VEHICLE: "per vehicle",
};

const STATUS_TEXT: Record<string, string> = {
  AWAITING_APPROVAL: "Waiting for your approval",
  APPROVED: "Approved (nothing is booked)",
  EXPIRED: "Expired",
  CANCELLED: "Cancelled",
};

/** Codes after which the terms on screen are out of date and the server's current ones are shown. */
const REFRESH_AFTER: readonly string[] = ["quote_changed", "quote_mismatch", "quote_expired"];

function newKey(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `ui-${random}`;
}

function errorText(error: unknown): string {
  if (error instanceof PlanningApiError) {
    if (error.status === null) {
      return "The planning server could not be reached.";
    }
    return error.detail ?? `The planning server refused the request (HTTP ${error.status}).`;
  }
  return "Something went wrong while talking to the planning server.";
}

interface CardProps {
  tripId: string;
  category: QuoteCategory;
  optionId: string;
  label: string;
}

/**
 * One option's booking intent: the exact terms, the approval and the disabled booking action.
 * Approving records agreement to these terms only; it never books. The terms shown are always the
 * server's latest, and the approval carries the fingerprint of exactly what is on screen.
 */
function IntentCard({ tripId, category, optionId, label }: CardProps) {
  const [intent, setIntent] = useState<BookingIntent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);
  // One key per card, so a repeated click returns the first intent instead of making another.
  const [key] = useState(newKey);

  async function prepare() {
    setBusy(true);
    setError(null);
    try {
      setIntent(await createIntent(tripId, category, optionId, key));
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (intent === null) {
      return;
    }
    setBusy(true);
    setError(null);
    setChanged(false);
    try {
      setIntent(await approveIntent(intent.id, intent.quoteContentHash));
    } catch (failure) {
      setError(errorText(failure));
      if (failure instanceof PlanningApiError && failure.code !== null && REFRESH_AFTER.includes(failure.code)) {
        // The terms moved. Show the server's current ones; the person decides again.
        try {
          setIntent(await getIntent(intent.id));
          setChanged(true);
        } catch {
          // Keep the message above; the old terms stay visible but cannot be approved again here.
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="card">
      <h4>{label}</h4>

      {intent === null && (
        <p>
          <button type="button" className="button button-secondary" disabled={busy} onClick={() => void prepare()}>
            Get the terms to approve
          </button>{" "}
          <span className="field-hint">Records nothing but the terms. Nothing is booked.</span>
        </p>
      )}

      {error !== null && (
        <StatusMessage kind="error" title="This could not be completed">
          {error}
        </StatusMessage>
      )}

      {intent !== null && (
        <div>
          {changed && (
            <StatusMessage kind="info" title="The terms changed">
              These are the provider&apos;s current terms. Look at them again before you decide.
            </StatusMessage>
          )}
          <p className="source-line">
            Status: <strong>{STATUS_TEXT[intent.status] ?? intent.status}</strong>
          </p>
          <dl className="facts">
            <div>
              <dt>Quoted price</dt>
              <dd>
                <MoneyText money={intent.quote.price} /> {BASIS_TEXT[intent.quote.price_basis]}
                {intent.quote.price_basis === "PER_TRAVELLER" &&
                  ` (${intent.travellers} ${intent.travellers === 1 ? "traveller" : "travellers"})`}
              </dd>
            </div>
            {intent.quote.fees.map((fee) => (
              <div key={fee.label}>
                <dt>{fee.label}</dt>
                <dd>
                  <MoneyText money={fee.amount} />
                </dd>
              </div>
            ))}
            <div>
              <dt>Availability</dt>
              <dd>
                <AvailabilityBadge availability={intent.quote.availability} />
              </dd>
            </div>
            <div>
              <dt>Cancellation</dt>
              <dd>{intent.quote.cancellation_terms ?? "Not supplied"}</dd>
            </div>
            <div>
              <dt>Quote valid until</dt>
              <dd>{formatUtcDateTime(intent.quote.valid_until)}</dd>
            </div>
            <div>
              <dt>Terms fingerprint</dt>
              <dd>
                <code>{intent.quoteContentHash.slice(0, 12)}</code>
              </dd>
            </div>
          </dl>
          <SourceLine source={intent.quote.source} />
          <p className="field-hint" role="note">
            {intent.notice}
          </p>

          {intent.status === "APPROVED" && intent.approval !== null && (
            <StatusMessage kind="info" title="Approved, and nothing is booked">
              You agreed to these exact terms until {formatUtcDateTime(intent.approval.expiresAt)}.
              After that you would have to approve again.
            </StatusMessage>
          )}
          {intent.status === "EXPIRED" && (
            <StatusMessage kind="info" title="These terms have expired">
              Get the terms again to see what is quoted now.
            </StatusMessage>
          )}

          <p className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy || intent.status !== "AWAITING_APPROVAL"}
              onClick={() => void approve()}
            >
              Approve these exact terms
            </button>
            <button type="button" className="button" disabled aria-describedby={`${intent.id}-why`}>
              Book (switched off)
            </button>
          </p>
          <p id={`${intent.id}-why`} className="field-hint">
            Booking is switched off in this project. Approving records your agreement only.
          </p>
        </div>
      )}
    </li>
  );
}

function transportLabel(option: TransportOption): string {
  return `${option.mode} ${option.operator_name ?? ""} ${option.service_label ?? ""}`.trim();
}

interface ServerBookingProps {
  run: PlanningRun;
}

/**
 * Approval step for the options the traveller chose. Development only, like the rest of the
 * server panel. Each card talks to the booking-intent API; none of them can book or pay.
 */
export function ServerBooking({ run }: ServerBookingProps) {
  const research = run.research;
  const selected = run.selected;
  if (research === null || selected === null) {
    return null;
  }
  const cards: CardProps[] = [];
  const outbound = research.transport.find((o) => o.id === selected.transportId);
  if (outbound !== undefined) {
    cards.push({ tripId: run.tripId, category: "TRANSPORT", optionId: outbound.id, label: `Outbound: ${transportLabel(outbound)}` });
  }
  const back = research.returnTransport.find((o) => o.id === selected.returnTransportId);
  if (back !== undefined) {
    cards.push({ tripId: run.tripId, category: "RETURN_TRANSPORT", optionId: back.id, label: `Return: ${transportLabel(back)}` });
  }
  const hotel: HotelOption | undefined = research.hotels.find((o) => o.id === selected.hotelId);
  if (hotel !== undefined) {
    cards.push({ tripId: run.tripId, category: "HOTEL", optionId: hotel.id, label: `Hotel: ${hotel.name}` });
  }
  if (cards.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby={`booking-${run.runId}`}>
      <h3 id={`booking-${run.runId}`}>Approval step (nothing is booked)</h3>
      <p className="field-hint">
        Each approval is for one option and its exact terms, and lasts a few minutes. There is no
        payment, and the booking action stays switched off.
      </p>
      <ul className="plain-list">
        {cards.map((card) => (
          <IntentCard key={`${card.category}-${card.optionId}`} {...card} />
        ))}
      </ul>
    </section>
  );
}
