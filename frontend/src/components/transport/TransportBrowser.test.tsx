import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { buildDemoOptions } from "../../demo/demoData";
import { EXAMPLE_FORM, validateTripForm } from "../../lib/tripRequest";
import { TransportBrowser } from "./TransportBrowser";

const validated = validateTripForm(EXAMPLE_FORM);
if (!validated.ok) {
  throw new Error("The example trip must be valid");
}
const demo = buildDemoOptions(validated.request);

function setup(selectedId: string | null = null) {
  const onToggleSelect = vi.fn<(id: string) => void>();
  render(
    <TransportBrowser
      options={demo.transport}
      quotes={demo.quotes}
      selectedId={selectedId}
      onToggleSelect={onToggleSelect}
    />,
  );
  return onToggleSelect;
}

const compareBox = (operator: string) =>
  screen.getByRole("checkbox", { name: new RegExp(`Compare.*${operator}`) });

describe("the three categories", () => {
  test("flights, trains and buses each have a heading with a count", () => {
    setup();

    expect(screen.getByRole("heading", { name: "Flights (3)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Trains (2)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buses (2)" })).toBeInTheDocument();
  });

  test("each card sits under its own category and names its operator", () => {
    setup();

    const flights = screen.getByRole("region", { name: "Flights (3)" });
    expect(within(flights).getByRole("heading", { name: /Demo Air/ })).toBeInTheDocument();
    expect(within(flights).queryByText(/Sample Rail Express/)).not.toBeInTheDocument();
    const buses = screen.getByRole("region", { name: "Buses (2)" });
    expect(within(buses).getByRole("heading", { name: /Example Travels/ })).toBeInTheDocument();
  });

  test("every card says MOCK and shows when its fictional data was retrieved", () => {
    setup();

    expect(screen.getAllByText(/MOCK · demo data/)).toHaveLength(7);
    expect(screen.getAllByText(/retrieved/).length).toBeGreaterThanOrEqual(7);
  });

  test("only the facts that fit a mode are shown on its cards", () => {
    setup();

    const trains = screen.getByRole("region", { name: "Trains (2)" });
    expect(within(trains).getAllByText("Class").length).toBe(2);
    expect(within(trains).queryByText("Cabin class")).not.toBeInTheDocument();
    expect(within(trains).queryByText("Seat type")).not.toBeInTheDocument();
    const flights = screen.getByRole("region", { name: "Flights (3)" });
    expect(within(flights).getAllByText("Cabin class").length).toBe(3);
  });

  test("an empty list says so", () => {
    render(
      <TransportBrowser options={[]} quotes={{}} selectedId={null} onToggleSelect={() => undefined} />,
    );

    expect(screen.getByText("No transport options")).toBeInTheDocument();
  });
});

describe("sorting", () => {
  const flightOrder = () =>
    within(screen.getByRole("region", { name: "Flights (3)" }))
      .getAllByRole("heading", { level: 4 })
      .map((heading) => heading.textContent ?? "");

  test("by price the cheapest flight is first, and by duration the longest one is last", () => {
    setup();
    expect(flightOrder()[0]).toContain("Example Airways");

    fireEvent.change(screen.getByLabelText("Sort each group by"), { target: { value: "duration" } });

    // Demo Air and Sample Wings both take 1h 45m, so they tie and keep their id order.
    expect(flightOrder().map((title) => title.split(" · ")[1])).toEqual([
      "Demo Air",
      "Sample Wings",
      "Example Airways",
    ]);
  });
});

describe("selecting", () => {
  test("choosing an option reports its id and an unavailable one cannot be chosen", () => {
    const onToggle = setup();

    fireEvent.click(screen.getByRole("button", { name: /Select Train.*Example Intercity/ }));

    expect(onToggle).toHaveBeenCalledWith("demo-train-2");
    expect(screen.queryByRole("button", { name: /Select Flight.*Demo Air/ })).not.toBeInTheDocument();
  });
});

describe("comparing", () => {
  test("one option asks for a second, two or three show a table", () => {
    setup();

    fireEvent.click(compareBox("Sample Wings"));
    expect(screen.getByText("Choose one more to compare")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    fireEvent.click(compareBox("Sample Rail Express"));
    expect(screen.getByRole("table", { name: /Comparison of 2 selected options/ })).toBeInTheDocument();
  });

  test("no more than three can be compared", () => {
    setup();
    fireEvent.click(compareBox("Sample Wings"));
    fireEvent.click(compareBox("Sample Rail Express"));
    fireEvent.click(compareBox("Example Travels"));

    expect(compareBox("Demo Coaches")).toBeDisabled();
    expect(compareBox("Sample Wings")).toBeEnabled();
  });

  test("rows for one mode read Not applicable for the others, and unrelated rows do not appear", () => {
    setup();
    fireEvent.click(compareBox("Sample Wings"));
    fireEvent.click(compareBox("Sample Rail Express"));

    const table = screen.getByRole("table");
    const cabin = within(table).getByRole("row", { name: /Cabin class/ });
    expect(within(cabin).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "Economy (demo)",
      "Not applicable",
    ]);
    expect(within(table).queryByRole("row", { name: /Seat type/ })).not.toBeInTheDocument();
  });

  test("marks the lowest price and the shortest journey, and states the basis is per traveller", () => {
    setup();
    fireEvent.click(compareBox("Sample Wings"));
    fireEvent.click(compareBox("Sample Rail Express"));

    const table = screen.getByRole("table");
    expect(within(within(table).getByRole("row", { name: /^Quoted price ₹/ })).getByText("(lowest)")).toBeInTheDocument();
    expect(within(table).getByText("(shortest)")).toBeInTheDocument();
    const comparison = screen.getByRole("region", { name: "Comparison" });
    expect(within(comparison).getByText(/per traveller, as quoted/)).toBeInTheDocument();
    expect(within(comparison).getByText(/not the trip estimate/)).toBeInTheDocument();
  });

  test("shows availability, cancellation, source and freshness for each option", () => {
    setup();
    fireEvent.click(compareBox("Example Airways"));
    fireEvent.click(compareBox("Demo Coaches"));

    const table = screen.getByRole("table");
    expect(within(table).getAllByText(/Availability unknown/).length).toBe(2);
    expect(within(table).getAllByText("Not supplied").length).toBeGreaterThan(0);
    expect(within(table).getAllByText(/MOCK · demo data/)).toHaveLength(2);
    expect(within(table).getAllByText(/retrieved/)).toHaveLength(2);
  });

  test("a bus with no stop count shows Not applicable, never zero", () => {
    setup();
    fireEvent.click(compareBox("Demo Coaches"));
    fireEvent.click(compareBox("Example Travels"));

    const stops = within(screen.getByRole("table")).getByRole("row", { name: /^Stops/ });
    expect(within(stops).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Not applicable", "3"]);
  });

  test("clearing the comparison removes the table and unticks the boxes", () => {
    setup();
    fireEvent.click(compareBox("Sample Wings"));
    fireEvent.click(compareBox("Sample Rail Express"));

    fireEvent.click(screen.getByRole("button", { name: "Clear comparison" }));

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(compareBox("Sample Wings")).not.toBeChecked();
  });
});
