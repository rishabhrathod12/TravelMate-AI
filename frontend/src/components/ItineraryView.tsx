import type { Itinerary } from "../contracts/types";
import { addDays, formatDay } from "../lib/dates";

interface ItineraryViewProps {
  itinerary: Itinerary;
  departureDate: string;
  /** Option IDs the itinerary may link to (the ones the user has selected). */
  optionNames: Record<string, string>;
  onShowOption: (optionId: string) => void;
}

/**
 * Days are numbered; the calendar date is worked out here from the departure
 * date, never written by whatever drafted the text.
 */
export function ItineraryView({
  itinerary,
  departureDate,
  optionNames,
  onShowOption,
}: ItineraryViewProps) {
  return (
    <div className="card">
      <p className="badge badge-mock">Sample itinerary · not verified</p>
      <ol className="itinerary">
        {itinerary.days.map((day) => {
          const headingId = `itinerary-day-${day.day_number}`;
          return (
            <li key={day.day_number}>
              <section aria-labelledby={headingId}>
                <h3 id={headingId}>
                  Day {day.day_number}
                  <span className="day-date"> · {formatDay(addDays(departureDate, day.day_number - 1))}</span>
                </h3>
                <ul className="activity-list">
                  {day.items.map((item) => (
                    <li key={item.title}>
                      <p className="activity-title">{item.title}</p>
                      {item.description !== null && <p className="activity-text">{item.description}</p>}
                      {item.option_id !== null && optionNames[item.option_id] !== undefined && (
                        <button
                          type="button"
                          className="button button-small button-quiet"
                          onClick={() => onShowOption(item.option_id as string)}
                        >
                          Show option: {optionNames[item.option_id]}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            </li>
          );
        })}
      </ol>
      {itinerary.notes !== null && <p className="field-hint">{itinerary.notes}</p>}
      <p className="field-hint">
        Costs are shown in the cost estimate above, not per activity. Locations and per-activity
        costs are not part of the itinerary model yet.
      </p>
    </div>
  );
}
