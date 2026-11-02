import { useId } from "react";

import type { WeatherInfo } from "../api/planning";
import { addDays, daysBetween, formatDay, isValidIsoDate } from "../lib/dates";
import { SourceLine } from "./SourceLine";
import { StatusMessage } from "./StatusMessage";

/** Dates that were asked for and have no forecast: the forecast horizon, reported, never filled in. */
function missingDays(weather: WeatherInfo): string[] {
  if (!isValidIsoDate(weather.start) || !isValidIsoDate(weather.end)) {
    return [];
  }
  const covered = new Set(weather.days.map((day) => day.day));
  const span = daysBetween(weather.start, weather.end);
  const missing: string[] = [];
  for (let offset = 0; offset <= span; offset += 1) {
    const day = addDays(weather.start, offset);
    if (!covered.has(day)) {
      missing.push(day);
    }
  }
  return missing;
}

function temperatureText(low: number | null, high: number | null): string {
  if (low !== null && high !== null) {
    return `${low}–${high} °C`;
  }
  if (high !== null) {
    return `up to ${high} °C`;
  }
  if (low !== null) {
    return `down to ${low} °C`;
  }
  return "temperature not given";
}

interface WeatherCardProps {
  weather: WeatherInfo;
}

/**
 * The forecast the planner researched for the destination, exactly as the server sent it, with its
 * source label. A day the forecast does not cover is listed as missing; nothing is estimated.
 */
export function WeatherCard({ weather }: WeatherCardProps) {
  const titleId = useId();
  const missing = missingDays(weather);
  return (
    <section className="card" aria-labelledby={titleId}>
      <h3 id={titleId}>{weather.location === "" ? "Weather" : `Weather in ${weather.location}`}</h3>
      {weather.source !== null && <SourceLine source={weather.source} />}
      {weather.days.length === 0 ? (
        <StatusMessage kind="info" title="No forecast available">
          {weather.emptyReason ?? "The weather provider gave no forecast for these dates."}
        </StatusMessage>
      ) : (
        <ul className="weather-days">
          {weather.days.map((day) => (
            <li key={day.day}>
              <strong>{formatDay(day.day)}</strong>: {day.summary} · {temperatureText(day.temperatureMinC, day.temperatureMaxC)}
              {day.rainChancePercent !== null && ` · ${day.rainChancePercent}% chance of rain`}
            </li>
          ))}
        </ul>
      )}
      {weather.days.length > 0 && missing.length > 0 && (
        <p className="field-hint">No forecast for: {missing.map((day) => formatDay(day)).join(", ")}.</p>
      )}
    </section>
  );
}
