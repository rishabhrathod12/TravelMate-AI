import type { HotelOption, Money, Quote, TransportOption } from "../contracts/types";
import { MODE_LABEL, transportFacts } from "../lib/transport";
import { AvailabilityBadge } from "./Badges";
import { MoneyText } from "./MoneyText";
import { SourceLine } from "./SourceLine";

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

interface CompareControl {
  checked: boolean;
  disabled: boolean;
  onChange: () => void;
}

interface TransportCardProps extends SelectableProps {
  option: TransportOption;
  quote: Quote | undefined;
  /** When given, the card offers a "Compare" checkbox. */
  compare?: CompareControl;
  /** Heading level of the card title; 4 when the card sits under a category heading. */
  headingLevel?: 3 | 4;
}

export function TransportCard({
  option,
  quote,
  selected,
  onToggle,
  compare,
  headingLevel = 3,
}: TransportCardProps) {
  const Heading = headingLevel === 4 ? "h4" : "h3";
  const title = `${MODE_LABEL[option.mode]}: ${option.origin.name} to ${option.destination.name}`;
  // The accessible name tells apart several options of one mode.
  const accessibleName = option.operator_name === null ? title : `${title}, ${option.operator_name}`;
  return (
    <article
      className={selected ? "card option-card is-selected" : "card option-card"}
      id={option.id}
      tabIndex={-1}
      aria-labelledby={`${option.id}-title`}
    >
      <header className="option-header">
        <Heading id={`${option.id}-title`}>
          {title}
          {option.operator_name !== null && (
            <span className="option-operator"> · {option.operator_name}</span>
          )}
        </Heading>
        <AvailabilityBadge availability={option.availability} />
      </header>
      <dl className="facts">
        {transportFacts(option).map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      <PriceBlock label="Quoted price" price={option.price} quote={quote} />
      <SourceLine source={option.source} />
      <SelectButton
        selected={selected}
        onToggle={onToggle}
        unavailable={option.availability === "UNAVAILABLE"}
        name={accessibleName}
      />
      {compare !== undefined && (
        <label className="compare-toggle">
          <input
            type="checkbox"
            checked={compare.checked}
            disabled={compare.disabled}
            onChange={compare.onChange}
          />{" "}
          Compare <span className="visually-hidden">{accessibleName}</span>
        </label>
      )}
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
