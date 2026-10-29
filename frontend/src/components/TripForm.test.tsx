import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { TripRequest } from "../contracts/types";
import { TripForm } from "./TripForm";

function setup() {
  const onSubmit = vi.fn<(request: TripRequest) => void>();
  render(<TripForm onSubmit={onSubmit} />);
  return onSubmit;
}

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function submitted(onSubmit: ReturnType<typeof setup>): TripRequest {
  expect(onSubmit).toHaveBeenCalledTimes(1);
  return onSubmit.mock.calls[0]?.[0] as TripRequest;
}

describe("TripForm fields", () => {
  test("every input has a label", () => {
    setup();

    expect(screen.getByLabelText("From")).toBeInTheDocument();
    expect(screen.getByLabelText("To")).toBeInTheDocument();
    expect(screen.getByLabelText("Departure date")).toBeInTheDocument();
    expect(screen.getByLabelText("Travellers")).toBeInTheDocument();
  });

  test("offers the three trip types as a radio group, round trip first selected", () => {
    setup();

    const group = screen.getByRole("group", { name: "Trip type" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /One-way/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Round trip/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Same-day return/ })).not.toBeChecked();
  });

  test("the return date is shown for a round trip only", () => {
    setup();
    expect(screen.getByLabelText("Return date")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /One-way/ }));
    expect(screen.queryByLabelText("Return date")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /Same-day return/ }));
    expect(screen.queryByLabelText("Return date")).not.toBeInTheDocument();
  });

  test("does not ask for a budget, which is not part of the trip request", () => {
    setup();

    expect(screen.queryByLabelText(/budget/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Budget is not part of the trip request yet/)).toBeInTheDocument();
  });
});

describe("TripForm validation", () => {
  test("an empty submit shows errors, does not submit and focuses the first problem", () => {
    const onSubmit = setup();

    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/fix 4 fields/i);
    expect(screen.getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("From")).toHaveAccessibleDescription("Enter where the trip starts.");
    expect(screen.getByLabelText("From")).toHaveFocus();
  });

  test("a return date before departure is explained", () => {
    const onSubmit = setup();
    fill("From", "Indore");
    fill("To", "Goa");
    fill("Departure date", "2026-12-05");
    fill("Return date", "2026-12-01");

    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText("The return date must be on or after the departure date."),
    ).toBeInTheDocument();
  });

  test("errors clear once the form is valid", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Use example trip/ }));
    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});

describe("TripForm submission", () => {
  test("the example trip is the Indore to Goa round trip", () => {
    const onSubmit = setup();

    fireEvent.click(screen.getByRole("button", { name: /Use example trip/ }));
    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    const request = submitted(onSubmit);
    expect(request.trip_type).toBe("ROUND_TRIP");
    expect(request.origin.name).toBe("Indore");
    expect(request.destination.name).toBe("Goa");
    expect(request.return_date).toBe("2026-12-05");
    expect(request.travellers).toHaveLength(2);
  });

  test("a one-way trip is sent with no return date", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByRole("radio", { name: /One-way/ }));
    fill("From", "Indore");
    fill("To", "Goa");
    fill("Departure date", "2026-12-01");

    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    const request = submitted(onSubmit);
    expect(request.trip_type).toBe("ONE_WAY");
    expect(request.return_date).toBeNull();
  });

  test("a same-day return is a round trip on one date", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByRole("radio", { name: /Same-day return/ }));
    fill("From", "Indore");
    fill("To", "Goa");
    fill("Departure date", "2026-12-01");

    fireEvent.click(screen.getByRole("button", { name: "Preview with demo data" }));

    const request = submitted(onSubmit);
    expect(request.trip_type).toBe("ROUND_TRIP");
    expect(request.return_date).toBe("2026-12-01");
  });

  test("clear empties the form", () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: /Use example trip/ }));
    expect(screen.getByLabelText("From")).toHaveValue("Indore");

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    expect(screen.getByLabelText("From")).toHaveValue("");
    expect(screen.getByLabelText("Travellers")).toHaveValue(1);
  });
});
