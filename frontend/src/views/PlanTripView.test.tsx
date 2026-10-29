import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { PlanTripView } from "./PlanTripView";

function previewExampleTrip() {
  fireEvent.click(screen.getByRole("button", { name: /Use example trip/ }));
  fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));
}

function selectButton(name: RegExp) {
  return screen.getByRole("button", { name });
}

describe("before a preview", () => {
  test("shows the form and an empty state, and no results", () => {
    render(<PlanTripView />);

    expect(screen.getByRole("heading", { level: 1, name: "Plan your trip" })).toBeInTheDocument();
    expect(screen.getByText("No preview yet")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Demo results" })).not.toBeInTheDocument();
  });
});

describe("after previewing the example trip", () => {
  test("shows labelled demo options and moves focus to the results", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    const results = screen.getByRole("heading", { name: "Demo results" });
    expect(results).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Transport options (demo)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hotel options (demo)" })).toBeInTheDocument();
    // One MOCK badge for each of the five demo options, and no other source label.
    expect(screen.getAllByText(/MOCK · demo data/)).toHaveLength(5);
    expect(screen.queryByText(/^LIVE$/)).not.toBeInTheDocument();
  });

  test("shows the request as JSON and says it is sent nowhere", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    expect(screen.getByText(/not sent anywhere/)).toBeInTheDocument();
    expect(screen.getByText(/"trip_type": "ROUND_TRIP"/)).toBeInTheDocument();
  });

  test("shows all three availability labels", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    expect(screen.getAllByText(/Available/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Unavailable/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Availability unknown/).length).toBeGreaterThan(0);
  });

  test("an unavailable option cannot be selected", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    expect(screen.getByText("Unavailable options cannot be selected.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Select Flight/ })).not.toBeInTheDocument();
  });

  test("prices say that their basis is not defined", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    expect(screen.getAllByText(/open question Q12/).length).toBeGreaterThan(0);
  });

  test("the sample itinerary is labelled and dated from the departure date", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    expect(screen.getByText(/Sample itinerary · not verified/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Day 1/ })).toHaveTextContent("1 Dec 2026");
    expect(screen.getByRole("heading", { name: /Day 5/ })).toHaveTextContent("5 Dec 2026");
  });
});

describe("selection, cost and approval preview", () => {
  test("with nothing selected there is nothing to approve", () => {
    render(<PlanTripView />);

    previewExampleTrip();

    expect(screen.getByText("Nothing to preview")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
  });

  test("the estimate totals the selected lines and lists what is left out", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    fireEvent.click(selectButton(/Select Train/));
    fireEvent.click(selectButton(/Select Sample Beach Resort/));

    const table = screen.getByRole("table", { name: /Demo cost estimate/ });
    const total = within(table).getByRole("row", { name: /Total of the lines shown/ });
    expect(total).toHaveTextContent("₹25,650.00");
    expect(within(table).getByText("Incomplete")).toBeInTheDocument();
    expect(screen.getByText("Not included in this total")).toBeInTheDocument();
    expect(screen.getByText(/Contingency: percentage and rounding rules/)).toBeInTheDocument();
  });

  test("selecting marks the card as pressed, and selecting again undoes it", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    const train = selectButton(/Select Train/);
    expect(train).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(train);
    expect(train).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(train);
    expect(train).toHaveAttribute("aria-pressed", "false");
  });

  test("the approval preview states nothing is booked and the approve button is disabled", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    fireEvent.click(selectButton(/Select Train/));

    expect(screen.getByText("Preview only. Nothing is booked.")).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: /Approve \(not available\)/ });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAccessibleDescription(/approval flow arrives in Milestone 10/);
    expect(screen.queryByRole("button", { name: /confirm|book now|pay/i })).not.toBeInTheDocument();
  });

  test("the preview marks the total as incomplete", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    fireEvent.click(selectButton(/Select Train/));

    expect(screen.getByText(/Estimated total so far \(incomplete\)/)).toBeInTheDocument();
  });

  test("clear selection resets the choices and the preview", () => {
    render(<PlanTripView />);
    previewExampleTrip();
    fireEvent.click(selectButton(/Select Train/));

    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));

    expect(selectButton(/Select Train/)).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Nothing to preview")).toBeInTheDocument();
  });

  test("a new preview forgets the earlier selection", () => {
    render(<PlanTripView />);
    previewExampleTrip();
    fireEvent.click(selectButton(/Select Train/));

    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    expect(selectButton(/Select Train/)).toHaveAttribute("aria-pressed", "false");
  });

  test("show option from the itinerary moves focus to that card", () => {
    render(<PlanTripView />);
    previewExampleTrip();
    fireEvent.click(selectButton(/Select Train/));

    fireEvent.click(screen.getByRole("button", { name: /Show option: train to Goa/ }));

    expect(document.getElementById("demo-train-1")).toHaveFocus();
  });
});

describe("one-way and same-day trips", () => {
  test.each([/One-way/, /Same-day return/])("%s explains that the stay length is undefined", (kind) => {
    render(<PlanTripView />);
    fireEvent.click(screen.getByRole("button", { name: /Use example trip/ }));
    fireEvent.click(screen.getByRole("radio", { name: kind }));

    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));
    fireEvent.click(selectButton(/Select Train/));
    fireEvent.click(selectButton(/Select Sample Beach Resort/));

    expect(screen.getByText("Stay length is not defined for this trip")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /Demo cost estimate/ });
    expect(within(table).queryByText(/Sample Beach Resort:/)).not.toBeInTheDocument();
    expect(screen.getByText(/stay length is not defined for one-way and same-day/)).toBeInTheDocument();
  });
});
