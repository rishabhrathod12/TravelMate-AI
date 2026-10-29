import type { CostEstimate, HotelOption, Quote, TransportOption } from "../contracts/types";
import { estimateTotal } from "../demo/demoData";
import { formatUtcDateTime } from "../lib/dates";
import { AvailabilityBadge } from "./Badges";
import { MoneyText } from "./MoneyText";
import { SourceLine } from "./SourceLine";

interface ApprovalPreviewProps {
  transport: TransportOption | null;
  hotel: HotelOption | null;
  quotes: Record<string, Quote>;
  estimate: CostEstimate;
  onClear: () => void;
}

function QuoteSummary({ title, quote }: { title: string; quote: Quote | undefined }) {
  if (quote === undefined) {
    return (
      <li>
        <p className="activity-title">{title}</p>
        <p className="field-hint">No quote is available for this option.</p>
      </li>
    );
  }
  return (
    <li>
      <p className="activity-title">{title}</p>
      <dl className="facts">
        <div>
          <dt>Quoted price</dt>
          <dd>
            <MoneyText money={quote.price} />
          </dd>
        </div>
        {quote.fees.map((fee) => (
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
            <AvailabilityBadge availability={quote.availability} />
          </dd>
        </div>
        <div>
          <dt>Cancellation</dt>
          <dd>{quote.cancellation_terms ?? "Not supplied"}</dd>
        </div>
        <div>
          <dt>Quote valid until</dt>
          <dd>{formatUtcDateTime(quote.valid_until)} (fictional demo time)</dd>
        </div>
      </dl>
      <SourceLine source={quote.source} />
    </li>
  );
}

/**
 * A read-only preview. There is no approval flow in the backend yet
 * (Milestone 10) and real booking is disabled, so nothing here can approve,
 * book or pay.
 */
export function ApprovalPreview({
  transport,
  hotel,
  quotes,
  estimate,
  onClear,
}: ApprovalPreviewProps) {
  const incomplete = estimate.missing_items.length > 0;
  return (
    <div className="card approval-preview">
      <div className="safety-callout" role="note">
        <p className="notice-title">Preview only. Nothing is booked.</p>
        <p>
          No booking is made and no payment is taken. Real booking is disabled in this project.
          When approval exists, it will apply to one exact quote and expire. An expired or
          changed quote can never be approved.
        </p>
      </div>

      <h3>Proposed selection</h3>
      <ul className="activity-list">
        {transport !== null && (
          <QuoteSummary
            title={`Transport: ${transport.mode.toLowerCase()} to ${transport.destination.name}`}
            quote={quotes[transport.id]}
          />
        )}
        {hotel !== null && <QuoteSummary title={`Hotel: ${hotel.name}`} quote={quotes[hotel.id]} />}
      </ul>

      <p className="approval-total">
        {incomplete ? "Estimated total so far (incomplete): " : "Estimated total: "}
        <MoneyText money={estimateTotal(estimate)} />
      </p>
      {incomplete && (
        <p className="field-hint">
          The total leaves out the items listed under the cost estimate. A real approval would
          show the full total.
        </p>
      )}

      <div className="button-row">
        <button type="button" className="button button-primary" disabled aria-describedby="approve-reason">
          Approve (not available)
        </button>
        <button type="button" className="button button-quiet" onClick={onClear}>
          Clear selection
        </button>
      </div>
      <p className="field-hint" id="approve-reason">
        Approval is not available: the approval flow arrives in Milestone 10 and booking is
        disabled.
      </p>
    </div>
  );
}
