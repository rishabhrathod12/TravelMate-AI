import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { ItineraryRequest } from "../contracts/types";
import { SamplePlan } from "./SamplePlan";

const REQUEST: ItineraryRequest = {
  destination: { name: "Goa" },
  start_date: "2026-11-07",
  days: 3,
  travellers: 2,
  preferences: null,
};

describe("SamplePlan", () => {
  test("says it is a scripted sample, not a model's plan, before anything else", () => {
    render(<SamplePlan request={REQUEST} />);

    expect(screen.getByRole("heading", { level: 2, name: "3-day plan for Goa" })).toBeInTheDocument();
    expect(screen.getByText(/not written by a language model/i)).toBeInTheDocument();
    expect(screen.getByText(/no prices, times or availability/i)).toBeInTheDocument();
  });

  test("works out each calendar date from the start date", () => {
    render(<SamplePlan request={REQUEST} />);

    expect(screen.getByRole("heading", { level: 3, name: /Day 1.*Sat, 7 Nov/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /Day 3.*Mon, 9 Nov/ })).toBeInTheDocument();
  });

  test("labels every line", () => {
    render(<SamplePlan request={REQUEST} />);

    const lines = screen.getAllByRole("listitem").filter((li) => li.querySelector(".activity-title"));
    expect(lines.length).toBeGreaterThan(0);
    for (const line of lines) {
      expect(line).toHaveTextContent("Scripted sample");
    }
  });

  test("shows the head count when given and offers nothing to book", () => {
    render(<SamplePlan request={REQUEST} />);

    expect(screen.getByText(/2 travellers/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
