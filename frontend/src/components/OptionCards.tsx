import type { HotelOption, Money, Quote, TransportMode, TransportOption } from "../contracts/types";
import { formatDuration, formatUtcDateTime } from "../lib/dates";
import { AvailabilityBadge } from "./Badges";
import { MoneyText } from "./MoneyText";
import { SourceLine } from "./SourceLine";

const MODE_LABEL: Record<TransportMode, string> = {
  FLIGHT: "Flight",
  TRAIN: "Train",
  BUS: "Bus",
  ROAD: "Road",
};

interface SelectableProps {
  selected: boolean;
  onToggle: () => void;
}

function PriceBlock({
  label,
  price,
  quote,
}: {
  label: string;
  price: Money | null;
  quote: Quote | undefined;
}) {
  return (
    <div className="price-block">
      <p className="price-label">{label}</p>
      {price === null ? (
        <p className="price-missing">Price not supplied</p>
      ) : (
        <p className="price-value">
          <MoneyText money={price} />
        </p>
      )}
      <p className="field-hint">As quoted. What it covers is not defined yet (open question Q12).</p>
      {quote !== undefined && quote.fees.length > 0 && (
        <ul className="fee-list">
          {quote.fees.map((fee) => (
            <li key={fee.label}>
              + {fee.label}: <MoneyText money={fee.amount} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SelectButton({
  selected,
  onToggle,
  unavailable,
  name,
}: SelectableProps & { unavailable: boolean; name: string }) {
  if (unavailable) {
    return (
      <p className="field-hint">Unavailable options cannot be selected.</p>
    );
  }
  return (
    <button
      type="button"
      className={selected ? "button button-primary" : "button button-secondary"}
      aria-pressed={selected}
      onClick={onToggle}
    >
      {selected ? "Selected" : "Select"}{" "}
      <span className="visually-hidden">{name}</span>
    </button>
  );
}

interface TransportCardProps extends SelectableProps {
  option: TransportOption;
  quote: Quote | undefined;
}

export function TransportCard({ option, quote, selected, onToggle }: TransportCardProps) {
  const title = `${MODE_LABEL[option.mode]}: ${option.origin.name} to ${option.destination.name}`;
  return (
    <article
      className={selected ? "card option-card is-selected" : "card option-card"}
      id={option.id}
      tabIndex={-1}
      aria-labelledby={`${option.id}-title`}
    >
      <header className="option-header">
        <h3 id={`${option.id}-title`}>{title}</h3>
        <AvailabilityBadge availability={option.availability} />
      </header>
      <dl className="facts">
        <div>
          <dt>Departs</dt>
          <dd>{formatUtcDateTime(option.departs_at)}</dd>
        </div>
        <div>
          <dt>Arrives</dt>
          <dd>{formatUtcDateTime(option.arrives_at)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{formatDuration(option.departs_at, option.arrives_at)}</dd>
        </div>
        <div>
          <dt>Stops</dt>
          <dd>{option.stops === null ? "Not supplied" : option.stops}</dd>
        </div>
        <div>
          <dt>Cancellation</dt>
          <dd>{option.cancellation_terms ?? "Not supplied"}</dd>
        </div>
      </dl>
      <PriceBlock label="Quoted price" price={option.price} quote={quote} />
      <SourceLine source={option.source} />
      <SelectButton
        selected={selected}
        onToggle={onToggle}
        unavailable={option.availability === "UNAVAILABLE"}
        name={title}
      />
    </article>
  );
}

interface HotelCardProps extends SelectableProps {
  option: HotelOption;
  quote: Quote | undefined;
}

export function HotelCard({ option, quote, selected, onToggle }: HotelCardProps) {
  return (
    <article
      className={selected ? "card option-card is-selected" : "card option-card"}
      id={option.id}
      tabIndex={-1}
      aria-labelledby={`${option.id}-title`}
    >
      <header className="option-header">
        <h3 id={`${option.id}-title`}>{option.name}</h3>
        <AvailabilityBadge availability={option.availability} />
      </header>
      <dl className="facts">
        <div>
          <dt>Location</dt>
          <dd>{option.location.name}</dd>
        </div>
        <div>
          <dt>Cancellation</dt>
          <dd>{option.cancellation_terms ?? "Not supplied"}</dd>
        </div>
      </dl>
      <PriceBlock label="Quoted nightly rate" price={option.nightly_rate} quote={quote} />
      <SourceLine source={option.source} />
      <SelectButton
        selected={selected}
        onToggle={onToggle}
        unavailable={option.availability === "UNAVAILABLE"}
        name={option.name}
      />
    </article>
  );
}
