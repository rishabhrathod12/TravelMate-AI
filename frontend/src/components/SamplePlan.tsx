import type { ItineraryRequest, SuggestionLabel } from "../contracts/types";
import { buildSamplePlan } from "../demo/sampleItinerary";
import { addDays, formatDay } from "../lib/dates";

interface SamplePlanProps {
  request: ItineraryRequest;
}

const LABEL_TEXT: Record<SuggestionLabel, string> = {
  SCRIPTED_SAMPLE: "Scripted sample",
  AI_SUGGESTION: "AI suggestion, not verified",
};

/**
 * The plan for an itinerary request. Until a real language model is connected (PRD Q19) this is a
 * scripted sample, and the banner and every line say so. Calendar dates are worked out here from
 * the start date; nothing in the plan states a price, time, availability or weather.
 */
export function SamplePlan({ request }: SamplePlanProps) {
  const days = buildSamplePlan(request);
  return (
    <section className="card sample-plan" aria-labelledby="sample-plan-title">
      <h2 id="sample-plan-title">
        {request.days}-day plan for {request.destination.name}
      </h2>
      <p className="badge badge-mock">
        Scripted sample · not written by a language model · not verified
      </p>
      <p className="field-hint">
        Starting {formatDay(request.start_date)}
        {request.travellers !== null
          ? ` · ${request.travellers} ${request.travellers === 1 ? "traveller" : "travellers"}`
          : ""}
        . A real model is not connected yet, so this shows the shape of a plan only. It has no
        prices, times or availability, and nothing here can be booked.
      </p>
      <ol className="itinerary">
        {days.map((day) => {
          const headingId = `sample-day-${day.day_number}`;
          return (
            <li key={day.day_number}>
              <section aria-labelledby={headingId}>
                <h3 id={headingId}>
                  Day {day.day_number}
                  <span className="day-date">
                    {" "}
                    · {formatDay(addDays(request.start_date, day.day_number - 1))}
                  </span>
                </h3>
                <ul className="activity-list">
                  {day.items.map((item) => (
                    <li key={item.title}>
                      <p className="activity-title">{item.title}</p>
                      <p className="field-hint">{LABEL_TEXT[item.label]}</p>
                    </li>
                  ))}
                </ul>
              </section>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
