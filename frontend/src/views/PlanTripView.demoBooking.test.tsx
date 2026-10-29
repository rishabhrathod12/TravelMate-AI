import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { PlanTripView } from "./PlanTripView";

function previewExampleTrip() {
  fireEvent.click(screen.getByRole("button", { name: /Use example trip/ }));
  fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));
}

const select = (name: RegExp) => fireEvent.click(screen.getByRole("button", { name }));

describe("transport and demo booking on the plan page", () => {
  test("flights, trains and buses are all offered, each marked MOCK", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    expect(screen.getByRole("heading", { name: "Flights (3)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Trains (2)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buses (2)" })).toBeInTheDocument();
    expect(screen.queryByText(/^LIVE$/)).not.toBeInTheDocument();
  });

  test("the demo booking section is separate from the approval preview and starts empty", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    const demo = screen.getByRole("region", { name: "Demo booking (simulation)" });
    expect(within(demo).getByText("DEMO · SIMULATION ONLY")).toBeInTheDocument();
    expect(within(demo).getByText(/Select a flight, train or bus/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Booking approval preview" })).toBeInTheDocument();
  });

  test("a full demo flow: select, understand, simulate; the real approval stays disabled", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    select(/Select Flight.*Sample Wings/);
    const demo = screen.getByRole("region", { name: "Demo booking (simulation)" });
    fireEvent.click(within(demo).getByRole("checkbox", { name: /I understand/ }));
    fireEvent.click(within(demo).getByRole("button", { name: "Simulate booking" }));

    const result = within(demo).getByRole("region", { name: "DEMO — NOT A REAL BOOKING" });
    expect(within(result).getByText("DEMO-BOOKING-001")).toBeInTheDocument();
    expect(within(result).getByText(/Sample Wings/)).toBeInTheDocument();

    // The simulation did not touch the real path: still preview-only and disabled.
    const approval = screen.getByRole("region", { name: "Booking approval preview" });
    expect(within(approval).getByText("Preview only. Nothing is booked.")).toBeInTheDocument();
    expect(within(approval).getByRole("button", { name: /Approve \(not available\)/ })).toBeDisabled();
    expect(within(approval).queryByText(/DEMO-BOOKING/)).not.toBeInTheDocument();
  });

  test("an option with unknown availability can be selected but not simulated", () => {
    render(<PlanTripView />);
    previewExampleTrip();

    select(/Select Bus.*Demo Coaches/);

    const demo = screen.getByRole("region", { name: "Demo booking (simulation)" });
    expect(within(demo).getByText(/Availability is unknown/)).toBeInTheDocument();
    expect(within(demo).queryByRole("button", { name: "Simulate booking" })).not.toBeInTheDocument();
  });

  test("a new preview does not carry an old tick into the next selection", () => {
    render(<PlanTripView />);
    previewExampleTrip();
    select(/Select Train.*Sample Rail Express/);
    const demo = screen.getByRole("region", { name: "Demo booking (simulation)" });
    fireEvent.click(within(demo).getByRole("checkbox", { name: /I understand/ }));

    select(/Select Train.*Example Intercity/);

    expect(within(demo).getByRole("checkbox", { name: /I understand/ })).not.toBeChecked();
  });
});
