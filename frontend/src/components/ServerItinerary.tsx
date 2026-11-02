import { useId, useState } from "react";

import { PlanningApiError, saveItineraryVersion } from "../api/planning";
import type { Itinerary } from "../contracts/types";
import { StatusMessage } from "./StatusMessage";

interface ServerItineraryProps {
  tripId: string;
  /** The draft the run wrote. */
  initial: Itinerary;
  warnings: string[];
}

function failureText(error: unknown): string {
  if (error instanceof PlanningApiError) {
    return error.status === null
      ? "The planning server could not be reached."
      : (error.detail ?? `The planning server refused the request (HTTP ${error.status}).`);
  }
  return "Something went wrong while talking to the planning server.";
}

/**
 * The itinerary draft, editable. Saving sends the edited days to the server as a new version made
 * by the traveller; the earlier versions are kept there. Items that refer to a chosen option keep
 * that reference, and the text of any item is the traveller's or a draft, never a provider fact.
 */
export function ServerItinerary({ tripId, initial, warnings }: ServerItineraryProps) {
  const [itinerary, setItinerary] = useState<Itinerary>(initial);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  const baseId = useId();

  function change(next: Itinerary) {
    setItinerary(next);
    setDirty(true);
    setSavedVersion(null);
  }

  function setItem(day: number, index: number, patch: { title?: string; description?: string | null }) {
    change({
      ...itinerary,
      days: itinerary.days.map((d, di) =>
        di !== day
          ? d
          : { ...d, items: d.items.map((item, ii) => (ii === index ? { ...item, ...patch } : item)) },
      ),
    });
  }

  function removeItem(day: number, index: number) {
    change({
      ...itinerary,
      days: itinerary.days.map((d, di) =>
        di !== day ? d : { ...d, items: d.items.filter((_, ii) => ii !== index) },
      ),
    });
  }

  function addItem(day: number) {
    change({
      ...itinerary,
      days: itinerary.days.map((d, di) =>
        di !== day ? d : { ...d, items: [...d.items, { title: "New item", description: null, option_id: null }] },
      ),
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = await saveItineraryVersion(tripId, itinerary);
      setSavedVersion(saved.version);
      setDirty(false);
    } catch (failure) {
      setError(failureText(failure));
    } finally {
      setSaving(false);
    }
  }

  const everyTitleFilled = itinerary.days.every((d) => d.items.every((item) => item.title.trim() !== ""));

  return (
    <section aria-labelledby={`${baseId}-title`}>
      <h3 id={`${baseId}-title`}>Itinerary draft (not verified)</h3>
      <p className="field-hint">
        A draft for you to edit. It holds no prices, times or availability from a provider, and
        nothing in it is booked.
      </p>
      {warnings.length > 0 && (
        <StatusMessage kind="info" title="Notes from the server">
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </StatusMessage>
      )}
      {itinerary.days.map((day, di) => (
        <fieldset key={day.day_number} className="card">
          <legend>Day {day.day_number}</legend>
          {day.items.length === 0 && <p className="field-hint">Nothing planned yet.</p>}
          {day.items.map((item, ii) => {
            const id = `${baseId}-${di}-${ii}`;
            return (
              <div key={id} className="itinerary-edit-row">
                <label htmlFor={`${id}-t`}>
                  Day {day.day_number} item {ii + 1} title
                </label>
                <input
                  id={`${id}-t`}
                  type="text"
                  value={item.title}
                  onChange={(event) => setItem(di, ii, { title: event.target.value })}
                />
                <label htmlFor={`${id}-d`}>
                  Day {day.day_number} item {ii + 1} notes
                </label>
                <input
                  id={`${id}-d`}
                  type="text"
                  value={item.description ?? ""}
                  onChange={(event) =>
                    setItem(di, ii, { description: event.target.value === "" ? null : event.target.value })
                  }
                />
                {item.option_id !== null && (
                  <span className="field-hint">Refers to a chosen option.</span>
                )}{" "}
                <button type="button" className="button button-small button-quiet" onClick={() => removeItem(di, ii)}>
                  Remove item {ii + 1} of day {day.day_number}
                </button>
              </div>
            );
          })}
          <button type="button" className="button button-small button-quiet" onClick={() => addItem(di)}>
            Add an item to day {day.day_number}
          </button>
        </fieldset>
      ))}
      {error !== null && (
        <StatusMessage kind="error" title="The itinerary was not saved">
          {error}
        </StatusMessage>
      )}
      {savedVersion !== null && (
        <StatusMessage kind="info" title={`Saved as version ${savedVersion}`}>
          Your edits are a new version; the earlier ones are kept on the server.
        </StatusMessage>
      )}
      <p>
        <button
          type="button"
          className="button button-secondary"
          disabled={saving || !dirty || !everyTitleFilled}
          onClick={() => void save()}
        >
          Save as a new version
        </button>
      </p>
    </section>
  );
}
