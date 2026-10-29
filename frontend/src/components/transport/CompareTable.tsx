import type { ReactNode } from "react";

import type { Quote, TransportOption } from "../../contracts/types";
import { formatDuration, formatUtcDateTime } from "../../lib/dates";
import {
  durationMinutes,
  MODE_LABEL,
  modeSpecificFact,
  quotedTotal,
} from "../../lib/transport";
import { AvailabilityBadge } from "../Badges";
import { MoneyText } from "../MoneyText";
import { SourceLine } from "../SourceLine";

interface CompareTableProps {
  options: readonly TransportOption[];
  quotes: Record<string, Quote>;
  onClear: () => void;
}

const NOT_SUPPLIED = "Not supplied";
const NOT_APPLICABLE = "Not applicable";

interface Row {
  label: string;
  cells: ReactNode[];
}

/** The smallest value among the options, only when at least two have one. Otherwise null. */
function lowest(values: (number | null)[]): number | null {
  const known = values.filter((value): value is number => value !== null);
  return known.length >= 2 ? Math.min(...known) : null;
}

/**
 * Side-by-side comparison of up to three options. Rows that belong to one mode (cabin class,
 * class, seat type) appear only when a compared option has that mode, and read "Not applicable"
 * for the others. Nothing here is a booking: it only reads the options.
 */
export function CompareTable({ options, quotes, onClear }: CompareTableProps) {
  const currencies = new Set(
    options.flatMap((option) => (option.price === null ? [] : [option.price.currency])),
  );
  // Prices in different currencies cannot be ranked; the project has no conversion.
  const rankable = currencies.size <= 1;
  const lowestPrice = rankable ? lowest(options.map((o) => o.price?.amount_minor ?? null)) : null;
  const shortest = lowest(options.map(durationMinutes));

  const modeFacts = (["FLIGHT", "TRAIN", "BUS"] as const).flatMap((mode) => {
    const sample = options.find((option) => option.mode === mode);
    const fact = sample === undefined ? null : modeSpecificFact(sample);
    return fact === null ? [] : [{ mode, label: fact.label }];
  });

  const rows: Row[] = [
    { label: "Type", cells: options.map((o) => MODE_LABEL[o.mode]) },
    { label: "Operator", cells: options.map((o) => o.operator_name ?? NOT_SUPPLIED) },
    { label: "Service", cells: options.map((o) => o.service_label ?? NOT_SUPPLIED) },
    { label: "Departs", cells: options.map((o) => formatUtcDateTime(o.departs_at)) },
    { label: "Arrives", cells: options.map((o) => formatUtcDateTime(o.arrives_at)) },
    {
      label: "Duration",
      cells: options.map((o) => (
        <>
          {formatDuration(o.departs_at, o.arrives_at)}
          {shortest !== null && durationMinutes(o) === shortest && <strong> (shortest)</strong>}
        </>
      )),
    },
    {
      label: "Stops",
      cells: options.map((o) => {
        if (o.mode === "BUS" && o.stops === null) {
          return NOT_APPLICABLE;
        }
        return o.stops === null ? NOT_SUPPLIED : String(o.stops);
      }),
    },
    ...modeFacts.map(({ mode, label }) => ({
      label,
      cells: options.map((o) => {
        if (o.mode !== mode) {
          return NOT_APPLICABLE;
        }
        return modeSpecificFact(o)?.value ?? NOT_SUPPLIED;
      }),
    })),
    {
      label: "Quoted price",
      cells: options.map((o) =>
        o.price === null ? (
          "Price not supplied"
        ) : (
          <>
            <MoneyText money={o.price} />
            {lowestPrice !== null && o.price.amount_minor === lowestPrice && (
              <strong> (lowest)</strong>
            )}
          </>
        ),
      ),
    },
    {
      label: "Quoted price plus sample fees",
      cells: options.map((o) => {
        const total = quotedTotal(o, quotes[o.id]);
        return total === null ? "Not available" : <MoneyText money={total} />;
      }),
    },
    {
      label: "Availability",
      cells: options.map((o) => <AvailabilityBadge availability={o.availability} />),
    },
    { label: "Cancellation", cells: options.map((o) => o.cancellation_terms ?? NOT_SUPPLIED) },
    { label: "Source and freshness", cells: options.map((o) => <SourceLine source={o.source} />) },
  ];

  return (
    <div className="compare-block">
      <div className="compare-scroll">
        <table className="compare-table">
          <caption>Comparison of {options.length} selected options (MOCK demo data)</caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="visually-hidden">Fact</span>
              </th>
              {options.map((option) => (
                <th scope="col" key={option.id}>
                  {MODE_LABEL[option.mode]}
                  {option.operator_name === null ? "" : `: ${option.operator_name}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                {row.cells.map((cell, index) => (
                  <td key={options[index]?.id ?? index}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="field-hint">
        Quoted prices are as quoted. What a price covers is not defined yet (open question Q12), and
        the sample fees exist only in this prototype. Quoted price plus fees is not the trip
        estimate: select one option to see the cost estimate, which lists what it leaves out.
      </p>
      <button type="button" className="button button-quiet button-small" onClick={onClear}>
        Clear comparison
      </button>
    </div>
  );
}
