import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { PlanningRun } from "../../api/planning";
import { AWAITING_SELECTION } from "../../test/planningFixtures";
import { RunChoices } from "./RunChoices";

function runFrom(body: typeof AWAITING_SELECTION): PlanningRun {
  const research = body.research as unknown as Record<string, { options: unknown[] }>;
  const waiting = body.waiting_for as unknown as { transport: string[]; return_transport: string[]; hotels: string[] };
  return {
    runId: "r1",
    tripId: "t1",
    status: "awaiting_selection",
    choices: { transport: waiting.transport, returnTransport: waiting.return_transport, hotels: waiting.hotels },
    research: {
      transport: research.transport?.options ?? [],
      returnTransport: research.return_transport?.options ?? [],
      hotels: research.hotels?.options ?? [],
    } as unknown as PlanningRun["research"],
    estimate: null,
    error: null,
    questions: [],
    selected: null,
    itinerary: null,
    itineraryWarnings: [],
    weather: null,
    providerIssues: [],
    notes: [],
  };
}

const RUN = runFrom(AWAITING_SELECTION);

describe("choosing options in the conversation", () => {
  test("shows each leg, the modes inside it, and what every option is, with its source label", () => {
    render(<RunChoices run={RUN} onChoose={() => undefined} />);

    expect(screen.getByRole("heading", { level: 3, name: "Choose your options" })).toBeInTheDocument();
    const outbound = within(screen.getByRole("group", { name: "Outbound" }));
    expect(outbound.getByText("Flights")).toBeInTheDocument();
    expect(outbound.getByText("Trains")).toBeInTheDocument();
    expect(outbound.getByText("FakeAir F1")).toBeInTheDocument();
    expect(outbound.getAllByText("per traveller").length).toBeGreaterThan(0);
    expect(screen.getByRole("group", { name: "Return" })).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Hotel" })).getByText("per room per night")).toBeInTheDocument();
    expect(screen.getAllByText(/Sample data/).length).toBeGreaterThanOrEqual(4);
  });

  test("the button stays off until every leg the trip has is chosen, then sends exactly those ids", () => {
    const onChoose = vi.fn();
    render(<RunChoices run={RUN} onChoose={onChoose} />);
    const button = screen.getByRole("button", { name: "Use these choices" });
    expect(button).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: /FakeRail T1/ }));
    fireEvent.click(screen.getByRole("radio", { name: /FakeAir F2/ }));
    expect(button).toBeDisabled(); // the hotel is still to choose

    fireEvent.click(screen.getByRole("radio", { name: /Sea View/ }));
    expect(button).toBeEnabled();
    fireEvent.click(button);

    expect(onChoose).toHaveBeenCalledWith({ transportId: "t", returnTransportId: "b", hotelId: "h1" });
  });

  test("says that choosing only tells the planner what to price, and offers nothing that books", () => {
    render(<RunChoices run={RUN} onChoose={() => undefined} />);

    expect(screen.getByText(/Nothing is booked/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /book|pay|approve/i })).not.toBeInTheDocument();
  });

  test("only the options the server offered can be chosen", () => {
    const narrowed: PlanningRun = { ...RUN, choices: { transport: ["a"], returnTransport: ["b"], hotels: ["h1"] } };
    render(<RunChoices run={narrowed} onChoose={() => undefined} />);

    expect(screen.getByRole("radio", { name: /FakeAir F1/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /FakeRail T1/ })).not.toBeInTheDocument();
  });

  test("a trip with no return leg or hotel asks only for the outbound choice", () => {
    const outboundOnly: PlanningRun = { ...RUN, choices: { transport: ["a"], returnTransport: [], hotels: [] } };
    const onChoose = vi.fn();
    render(<RunChoices run={outboundOnly} onChoose={onChoose} />);

    expect(screen.queryByRole("group", { name: "Return" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Hotel" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /FakeAir F1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Use these choices" }));

    expect(onChoose).toHaveBeenCalledWith({ transportId: "a", returnTransportId: null, hotelId: null });
  });

  test("a private taxi is offered under its own heading and says its price is per vehicle", () => {
    const withRoad: PlanningRun = {
      ...RUN,
      choices: { transport: ["a", "road1"], returnTransport: [], hotels: [] },
      research: {
        ...(RUN.research as NonNullable<PlanningRun["research"]>),
        transport: [
          ...((RUN.research as NonNullable<PlanningRun["research"]>).transport),
          { ...(RUN.research as NonNullable<PlanningRun["research"]>).transport[0], id: "road1", mode: "ROAD", operator_name: "FakeCabs", service_label: "Sedan", details: { kind: "ROAD", vehicle_type: "Sedan", passenger_capacity: 4 } },
        ],
      } as PlanningRun["research"],
    };
    render(<RunChoices run={withRoad} onChoose={() => undefined} />);

    expect(screen.getByRole("radio", { name: /FakeCabs Sedan/ })).toBeInTheDocument();
    expect(screen.getByText("Private taxis")).toBeInTheDocument();
    expect(screen.getByText("per vehicle (4 seats)")).toBeInTheDocument();
  });

  test("an unreadable run shows nothing rather than guessing", () => {
    const { container } = render(<RunChoices run={{ ...RUN, choices: null }} onChoose={() => undefined} />);

    expect(container).toBeEmptyDOMElement();
  });
});
