import { useId, useState } from "react";

import type { CostEstimate, Quote, TransportOption, TripRequest } from "../../contracts/types";
import {
  checkEligibility,
  DEMO_BOOKING_LABEL,
  DEMO_DISCLAIMERS,
  type DemoBooking,
} from "../../demoBooking/demoBooking";
import { useDemoBooking } from "../../demoBooking/useDemoBooking";
import { formatUtcDateTime } from "../../lib/dates";
import { MODE_LABEL, quotedTotal } from "../../lib/transport";
import { MoneyText } from "../MoneyText";
import { SourceLine } from "../SourceLine";
import { StatusMessage } from "../StatusMessage";

interface DemoBookingPanelProps {
  transport: TransportOption | null;
  quote: Quote | undefined;
  request: TripRequest;
  estimate: CostEstimate;
}

function Disclaimers() {
  return (
    <ul className="demo-disclaimers">
      {DEMO_DISCLAIMERS.map((text) => (
        <li key={text}>{text}</li>
      ))}
    </ul>
  );
}

function DemoResult({ booking, duplicate }: { booking: DemoBooking; duplicate: boolean }) {
  return (
    <section className="demo-result" aria-labelledby="demo-result-title">
      <p className="demo-stamp" id="demo-result-title" role="status">
        {DEMO_BOOKING_LABEL}
      </p>
      <p className="demo-reference">
        Sample reference: <strong>{booking.reference}</strong>
      </p>
      <p className="field-hint">
        A sample number for this browser session only. It repeats after a reload and is not a PNR,
        a ticket number or a provider confirmation.
      </p>
      {duplicate && (
        <p className="demo-duplicate" role="status">
          This selection was already simulated. No second demo booking was created.
        </p>
      )}
      <dl className="facts">
        <div>
          <dt>Service</dt>
          <dd>
            {MODE_LABEL[booking.mode]}
            {booking.operator_name === null ? "" : `: ${booking.operator_name}`}
            {booking.service_label === null ? "" : ` (${booking.service_label})`}
          </dd>
        </div>
        <div>
          <dt>Route</dt>
          <dd>
            {booking.origin} to {booking.destination}
          </dd>
        </div>
        <div>
          <dt>Departs</dt>
          <dd>{formatUtcDateTime(booking.departs_at)}</dd>
        </div>
        <div>
          <dt>Arrives</dt>
          <dd>{formatUtcDateTime(booking.arrives_at)}</dd>
        </div>
        <div>
          <dt>Quoted price plus sample fees</dt>
          <dd>
            <MoneyText money={booking.quoted_total} />
          </dd>
        </div>
      </dl>
      <SourceLine source={booking.source} />
      <p>
        This is a simulation. Nothing was sent to any airline, railway, bus operator or payment
        service.
      </p>
      <Disclaimers />
    </section>
  );
}

/**
 * The demo-booking simulation, kept apart from the real approval preview. It never says
 * approve, book now or pay, and it has no way to reach a provider.
 */
export function DemoBookingPanel({ transport, quote, request, estimate }: DemoBookingPanelProps) {
  const demo = useDemoBooking();
  const [understood, setUnderstood] = useState<string | null>(null);
  // The reference created by a click in this panel; any other result was made earlier.
  const [justCreated, setJustCreated] = useState<string | null>(null);
  // Forget "just created" as soon as the selection changes, so coming back to an option that was
  // simulated earlier is reported as already done.
  const selectedId = transport?.id ?? null;
  const [shownFor, setShownFor] = useState(selectedId);
  if (shownFor !== selectedId) {
    setShownFor(selectedId);
    setJustCreated(null);
  }
  const checkboxId = useId();

  const eligibility = checkEligibility(transport, quote);
  const existing = transport === null ? undefined : demo.find(transport.id, request);
  // The tick belongs to one selection, so choosing another option starts unticked.
  const ticked = transport !== null && understood === transport.id;
  const total = transport === null ? null : quotedTotal(transport, quote);

  return (
    <div className="card demo-booking">
      <p className="demo-ribbon">DEMO · SIMULATION ONLY</p>
      <p className="notice-title">This does not book anything.</p>
      <Disclaimers />

      {transport === null || !eligibility.ok ? (
        <StatusMessage kind={transport === null ? "empty" : "info"} title="No demo booking to try">
          {eligibility.ok ? "Select a transport option." : eligibility.reason}
        </StatusMessage>
      ) : (
        <>
          <h3>Review the demo details</h3>
          <dl className="facts">
            <div>
              <dt>Service</dt>
              <dd>
                {MODE_LABEL[transport.mode]}
                {transport.operator_name === null ? "" : `: ${transport.operator_name}`}
                {transport.service_label === null ? "" : ` (${transport.service_label})`}
              </dd>
            </div>
            <div>
              <dt>Route</dt>
              <dd>
                {transport.origin.name} to {transport.destination.name}
              </dd>
            </div>
            <div>
              <dt>Departs</dt>
              <dd>{formatUtcDateTime(transport.departs_at)}</dd>
            </div>
            <div>
              <dt>Quoted price plus sample fees</dt>
              <dd>{total === null ? "Not available" : <MoneyText money={total} />}</dd>
            </div>
          </dl>
          {estimate.missing_items.length > 0 && (
            <p className="field-hint">
              This is not the trip estimate. The cost estimate above is incomplete and lists what
              it leaves out. The quoted price is for one traveller.
            </p>
          )}

          {existing === undefined ? (
            <>
              <div className="field">
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={ticked}
                  onChange={(event) => setUnderstood(event.target.checked ? transport.id : null)}
                />{" "}
                <label htmlFor={checkboxId}>
                  I understand this is a simulation only. Nothing is reserved, ticketed or paid.
                </label>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={!ticked}
                  onClick={() => {
                    const result = demo.submit(transport, quote, request);
                    if (!result.duplicate) {
                      setJustCreated(result.booking.reference);
                    }
                  }}
                >
                  Simulate booking
                </button>
              </div>
            </>
          ) : (
            <DemoResult booking={existing} duplicate={existing.reference !== justCreated} />
          )}
        </>
      )}
    </div>
  );
}
