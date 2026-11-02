import { useId, useState } from "react";

import type { PlanningRun, Selection } from "../../api/planning";
import type { HotelOption, Money, TransportMode, TransportOption } from "../../contracts/types";
import { formatDuration, formatUtcDateTime } from "../../lib/dates";
import { MODE_PLURAL, sortTransport } from "../../lib/transport";
import { AvailabilityBadge, ProvenanceBadge } from "../Badges";
import { MoneyText } from "../MoneyText";

/** Modes in display order. Any other mode (for example road) follows, so no option is ever dropped. */
const MODE_ORDER: readonly TransportMode[] = ["FLIGHT", "TRAIN", "BUS"];

function groupedByMode(options: readonly TransportOption[]) {
  const present = [...new Set(options.map((option) => option.mode))];
  const modes = [
    ...MODE_ORDER.filter((mode) => present.includes(mode)),
    ...present.filter((mode) => !MODE_ORDER.includes(mode)),
  ];
  return modes.map((mode) => ({
    mode,
    options: sortTransport(
      options.filter((option) => option.mode === mode),
      "price",
    ),
  }));
}

interface RowProps {
  name: string;
  value: string;
  checked: boolean;
  onChoose: () => void;
  title: string;
  detail: string;
  price: Money | null;
  priceNote: string;
  option: TransportOption | HotelOption;
}

function ChoiceRow({ name, value, checked, onChoose, title, detail, price, priceNote, option }: RowProps) {
  return (
    <label className="choice-row">
      <input type="radio" name={name} value={value} checked={checked} onChange={onChoose} />
      <span className="choice-body">
        <strong>{title}</strong>
        {detail !== "" && <span className="field-hint">{detail}</span>}
        <span className="choice-meta">
          {price === null ? <span>No price</span> : <MoneyText money={price} />}
          <span className="field-hint">{priceNote}</span>
          <ProvenanceBadge provenance={option.source.provenance} />
          <AvailabilityBadge availability={option.availability} />
        </span>
      </span>
    </label>
  );
}

function transportDetail(option: TransportOption): string {
  return `${formatUtcDateTime(option.departs_at)} → ${formatUtcDateTime(option.arrives_at)} (${formatDuration(option.departs_at, option.arrives_at)})`;
}

function transportTitle(option: TransportOption): string {
  return `${option.operator_name ?? ""} ${option.service_label ?? ""}`.trim() || MODE_PLURAL[option.mode];
}

interface LegProps {
  legend: string;
  name: string;
  options: readonly TransportOption[];
  allowed: readonly string[];
  chosen: string | null;
  onChoose: (id: string) => void;
}

function TransportLeg({ legend, name, options, allowed, chosen, onChoose }: LegProps) {
  const shown = options.filter((option) => allowed.includes(option.id));
  if (shown.length === 0) {
    return null;
  }
  return (
    <fieldset className="card">
      <legend>{legend}</legend>
      {groupedByMode(shown).map((group) => (
        <div key={group.mode}>
          <p className="choice-group">{MODE_PLURAL[group.mode]}</p>
          {group.options.map((option) => (
            <ChoiceRow
              key={option.id}
              name={name}
              value={option.id}
              checked={chosen === option.id}
              onChoose={() => onChoose(option.id)}
              title={transportTitle(option)}
              detail={transportDetail(option)}
              price={option.price}
              priceNote="per traveller"
              option={option}
            />
          ))}
        </div>
      ))}
    </fieldset>
  );
}

interface RunChoicesProps {
  run: PlanningRun;
  onChoose: (selection: Selection) => void;
}

/**
 * The options the planner found, as choices inside the conversation. Only the options the server
 * offered can be chosen. Choosing here only tells the planner which ones to price: it books and
 * approves nothing.
 */
export function RunChoices({ run, onChoose }: RunChoicesProps) {
  const titleId = useId();
  const [selection, setSelection] = useState<Selection>({
    transportId: null,
    returnTransportId: null,
    hotelId: null,
  });
  const choices = run.choices;
  const research = run.research;
  if (choices === null || research === null) {
    return null;
  }
  const needsReturn = choices.returnTransport.length > 0;
  const needsHotel = choices.hotels.length > 0;
  const hotels = research.hotels.filter((hotel) => choices.hotels.includes(hotel.id));
  const ready =
    selection.transportId !== null &&
    (!needsReturn || selection.returnTransportId !== null) &&
    (!needsHotel || selection.hotelId !== null);

  return (
    <section aria-labelledby={titleId}>
      <h3 id={titleId}>Choose your options</h3>
      <TransportLeg
        legend="Outbound"
        name="run-outbound"
        options={research.transport}
        allowed={choices.transport}
        chosen={selection.transportId}
        onChoose={(id) => setSelection({ ...selection, transportId: id })}
      />
      <TransportLeg
        legend="Return"
        name="run-return"
        options={research.returnTransport}
        allowed={choices.returnTransport}
        chosen={selection.returnTransportId}
        onChoose={(id) => setSelection({ ...selection, returnTransportId: id })}
      />
      {hotels.length > 0 && (
        <fieldset className="card">
          <legend>Hotel</legend>
          {hotels.map((hotel) => (
            <ChoiceRow
              key={hotel.id}
              name="run-hotel"
              value={hotel.id}
              checked={selection.hotelId === hotel.id}
              onChoose={() => setSelection({ ...selection, hotelId: hotel.id })}
              title={hotel.name}
              detail=""
              price={hotel.nightly_rate}
              priceNote="per room per night"
              option={hotel}
            />
          ))}
        </fieldset>
      )}
      <p>
        <button type="button" className="button button-secondary" disabled={!ready} onClick={() => onChoose(selection)}>
          Use these choices
        </button>{" "}
        <span className="field-hint">This only tells the planner what to price. Nothing is booked.</span>
      </p>
    </section>
  );
}
