import { useId, useState } from "react";

import type { Quote, TransportOption } from "../../contracts/types";
import {
  groupByMode,
  MODE_PLURAL,
  sortTransport,
  type TransportSortKey,
} from "../../lib/transport";
import { StatusMessage } from "../StatusMessage";
import { TransportCard } from "../OptionCards";
import { CompareTable } from "./CompareTable";

export const MAX_COMPARED = 3;

interface TransportBrowserProps {
  options: readonly TransportOption[];
  quotes: Record<string, Quote>;
  selectedId: string | null;
  onToggleSelect: (optionId: string) => void;
}

/** Flights, trains and buses in separate groups, with sorting and a side-by-side comparison. */
export function TransportBrowser({
  options,
  quotes,
  selectedId,
  onToggleSelect,
}: TransportBrowserProps) {
  const [sortKey, setSortKey] = useState<TransportSortKey>("price");
  const [chosen, setChosen] = useState<string[]>([]);
  const sortId = useId();

  const known = new Set(options.map((option) => option.id));
  const compareIds = chosen.filter((id) => known.has(id));
  const compared = compareIds
    .map((id) => options.find((option) => option.id === id))
    .filter((option): option is TransportOption => option !== undefined);

  function toggleCompare(optionId: string) {
    setChosen(
      compareIds.includes(optionId)
        ? compareIds.filter((id) => id !== optionId)
        : [...compareIds, optionId].slice(0, MAX_COMPARED),
    );
  }

  const groups = groupByMode(sortTransport(options, sortKey));

  return (
    <div className="transport-browser">
      <div className="field transport-sort">
        <label htmlFor={sortId}>Sort each group by</label>
        <select
          id={sortId}
          value={sortKey}
          onChange={(event) => setSortKey(event.target.value === "duration" ? "duration" : "price")}
        >
          <option value="price">Quoted price, lowest first</option>
          <option value="duration">Duration, shortest first</option>
        </select>
        <p className="field-hint">
          Options with no price come last. Tick “Compare” on two or three options to see them side
          by side.
        </p>
      </div>

      {groups.map((group) => (
        <section key={group.mode} aria-labelledby={`group-${group.mode}`} className="transport-group">
          <h3 id={`group-${group.mode}`}>
            {MODE_PLURAL[group.mode]} ({group.options.length})
          </h3>
          <div className="card-grid">
            {group.options.map((option) => (
              <TransportCard
                key={option.id}
                option={option}
                quote={quotes[option.id]}
                selected={option.id === selectedId}
                onToggle={() => onToggleSelect(option.id)}
                headingLevel={4}
                compare={{
                  checked: compareIds.includes(option.id),
                  disabled: !compareIds.includes(option.id) && compareIds.length >= MAX_COMPARED,
                  onChange: () => toggleCompare(option.id),
                }}
              />
            ))}
          </div>
        </section>
      ))}

      {groups.length === 0 && (
        <StatusMessage kind="empty" title="No transport options">
          No flights, trains or buses were found for this trip.
        </StatusMessage>
      )}

      {compared.length === 1 && (
        <StatusMessage kind="info" title="Choose one more to compare">
          Tick “Compare” on a second option (up to {MAX_COMPARED}).
        </StatusMessage>
      )}
      {compared.length >= 2 && (
        <section aria-labelledby="compare-title">
          <h3 id="compare-title">Comparison</h3>
          <CompareTable options={compared} quotes={quotes} onClear={() => setChosen([])} />
        </section>
      )}
    </div>
  );
}
