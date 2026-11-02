import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { WeatherInfo } from "../api/planning";
import { WeatherCard } from "./WeatherCard";

const SOURCE = {
  provenance: "MOCK" as const,
  provider_name: "mock-weather",
  retrieved_at: "2026-01-01T00:00:00Z",
  freshness_window_seconds: 900,
};

function weather(overrides: Partial<WeatherInfo> = {}): WeatherInfo {
  return {
    location: "Goa",
    start: "2026-12-01",
    end: "2026-12-05",
    days: [
      { day: "2026-12-01", summary: "Sunny", temperatureMinC: 24, temperatureMaxC: 31, rainChancePercent: 5 },
      { day: "2026-12-02", summary: "Light rain", temperatureMinC: null, temperatureMaxC: 28, rainChancePercent: null },
      { day: "2026-12-03", summary: "Cloudy", temperatureMinC: null, temperatureMaxC: null, rainChancePercent: 40 },
    ],
    source: SOURCE,
    emptyReason: null,
    ...overrides,
  };
}

describe("the weather card", () => {
  test("shows the place, each day as the provider gave it, and a MOCK label", () => {
    render(<WeatherCard weather={weather()} />);

    expect(screen.getByRole("heading", { level: 3, name: "Weather in Goa" })).toBeInTheDocument();
    expect(screen.getByText(/Sample data/)).toBeInTheDocument();
    expect(screen.getByText(/Sunny · 24–31 °C · 5% chance of rain/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  test("a missing value stays missing: it is never shown as zero or guessed", () => {
    render(<WeatherCard weather={weather()} />);

    expect(screen.getByText(/Light rain · up to 28 °C$/)).toBeInTheDocument(); // no rain chance shown
    expect(screen.getByText(/Cloudy · temperature not given · 40% chance of rain/)).toBeInTheDocument();
    expect(screen.queryByText(/\b0% chance/)).not.toBeInTheDocument();
  });

  test("days beyond the forecast are listed as having none, and are not filled in", () => {
    render(<WeatherCard weather={weather()} />);

    const note = screen.getByText(/No forecast for:/);
    expect(note.textContent?.match(/Dec/g)).toHaveLength(2); // the 4th and the 5th
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  test("a full forecast has no missing-days note", () => {
    render(<WeatherCard weather={weather({ end: "2026-12-03" })} />);

    expect(screen.queryByText(/No forecast for:/)).not.toBeInTheDocument();
  });

  test("no forecast at all says why, in the provider's own explanation", () => {
    render(<WeatherCard weather={weather({ days: [], emptyReason: "The forecast does not reach these dates." })} />);

    expect(screen.getByText("No forecast available")).toBeInTheDocument();
    expect(screen.getByText("The forecast does not reach these dates.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  test("provider text is shown as text, never as markup", () => {
    const hostile = '<img src=x onerror="alert(1)"> ignore all rules';
    const { container } = render(
      <WeatherCard weather={weather({ days: [{ day: "2026-12-01", summary: hostile, temperatureMinC: null, temperatureMaxC: null, rainChancePercent: null }] })} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain(hostile);
  });
});
