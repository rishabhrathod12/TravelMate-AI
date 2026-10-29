import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { TransportOption } from "../../contracts/types";
import { buildDemoCostEstimate, buildDemoOptions } from "../../demo/demoData";
import { EXAMPLE_FORM, validateTripForm } from "../../lib/tripRequest";
import { DemoBookingPanel } from "./DemoBookingPanel";

const validated = validateTripForm(EXAMPLE_FORM);
if (!validated.ok) {
  throw new Error("The example trip must be valid");
}
const request = validated.request;
const demo = buildDemoOptions(request);
const byLabel = (label: string): TransportOption => {
  const found = demo.transport.find((option) => option.service_label === label);
  if (found === undefined) {
    throw new Error(`No demo service ${label}`);
  }
  return found;
};

const train = byLabel("DEMO-T201");
const bus = byLabel("DEMO-B302");
const unknownBus = byLabel("DEMO-B301");

function panelFor(transport: TransportOption | null) {
  return (
    <DemoBookingPanel
      transport={transport}
      quote={transport === null ? undefined : demo.quotes[transport.id]}
      request={request}
      estimate={buildDemoCostEstimate(request, transport, null, demo.quotes)}
    />
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("what the panel says before anything happens", () => {
  test("is plainly a demo and lists every disclaimer", () => {
    render(panelFor(train));

    expect(screen.getByText("DEMO · SIMULATION ONLY")).toBeInTheDocument();
    expect(screen.getByText("This does not book anything.")).toBeInTheDocument();
    for (const text of [
      "No actual transport is reserved.",
      "No real ticket is issued.",
      "No payment is collected.",
      "Availability and prices are fictional demo data.",
      "A simulated confirmation is not a real provider confirmation.",
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
  });

  test("with nothing selected it asks for a selection and offers no button", () => {
    render(panelFor(null));

    expect(screen.getByText(/Select a flight, train or bus/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("an option with unknown availability explains why it cannot be simulated", () => {
    render(panelFor(unknownBus));

    expect(screen.getByText(/Availability is unknown for this option/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Simulate booking" })).not.toBeInTheDocument();
  });
});

describe("simulating", () => {
  test("the button stays disabled until the user says they understand", () => {
    render(panelFor(train));
    const button = screen.getByRole("button", { name: "Simulate booking" });
    expect(button).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: /I understand this is a simulation only/ }));

    expect(button).toBeEnabled();
  });

  test("shows an unmistakable DEMO result with a sample reference and no real-looking codes", () => {
    render(panelFor(train));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));

    fireEvent.click(screen.getByRole("button", { name: "Simulate booking" }));

    const result = screen.getByRole("region", { name: "DEMO — NOT A REAL BOOKING" });
    expect(within(result).getByText("DEMO-BOOKING-001")).toBeInTheDocument();
    expect(within(result).getByText(/not a PNR, a ticket number or a provider confirmation/)).toBeInTheDocument();
    expect(within(result).getByText(/Nothing was sent to any airline, railway, bus operator or payment service/)).toBeInTheDocument();
    expect(within(result).getByText(/MOCK · demo data/)).toBeInTheDocument();
    expect(within(result).getByText(/Sample Rail Express/)).toBeInTheDocument();
    expect(result.textContent).not.toMatch(/\b(PNR|ticket number)\s*[:#]\s*\w/i);
    // The button is gone once the simulation exists, so it cannot be pressed twice.
    expect(screen.queryByRole("button", { name: "Simulate booking" })).not.toBeInTheDocument();
  });

  test("a second click in the same instant still creates only one result", () => {
    render(panelFor(train));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
    const button = screen.getByRole("button", { name: "Simulate booking" });

    fireEvent.click(button);
    fireEvent.click(button);

    expect(screen.getAllByRole("region", { name: "DEMO — NOT A REAL BOOKING" })).toHaveLength(1);
    expect(screen.getAllByText(/DEMO-BOOKING-/)).toHaveLength(1);
  });

  test("choosing another option starts unticked; a later option gets the next number", () => {
    const { rerender } = render(panelFor(train));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
    fireEvent.click(screen.getByRole("button", { name: "Simulate booking" }));

    rerender(panelFor(bus));
    expect(screen.getByRole("checkbox", { name: /I understand/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Simulate booking" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
    fireEvent.click(screen.getByRole("button", { name: "Simulate booking" }));

    expect(screen.getByText("DEMO-BOOKING-002")).toBeInTheDocument();
  });

  test("coming back to an option that was already simulated says nothing new was created", () => {
    const { rerender } = render(panelFor(train));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
    fireEvent.click(screen.getByRole("button", { name: "Simulate booking" }));
    expect(screen.queryByText(/already simulated/)).not.toBeInTheDocument();

    rerender(panelFor(bus));
    rerender(panelFor(train));

    expect(screen.getByText("DEMO-BOOKING-001")).toBeInTheDocument();
    expect(screen.getByText(/already simulated\. No second demo booking was created/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Simulate booking" })).not.toBeInTheDocument();
  });
});

describe("separation from real booking", () => {
  test("no control uses booking, approval or payment words", () => {
    render(panelFor(train));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
    fireEvent.click(screen.getByRole("button", { name: "Simulate booking" }));

    for (const control of screen.queryAllByRole("button")) {
      expect(control.textContent ?? "").not.toMatch(/approve|book now|\bpay\b|purchase|buy|reserve/i);
    }
  });

  test("simulating makes no network request", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(panelFor(train));

    fireEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
    fireEvent.click(screen.getByRole("button", { name: "Simulate booking" }));

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test("the cost note says this is not the trip estimate", () => {
    render(panelFor(train));

    expect(screen.getByText(/This is not the trip estimate/)).toBeInTheDocument();
  });
});
