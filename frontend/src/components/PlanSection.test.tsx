import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { ChatApiError } from "../api/chat";
import type { ItineraryRequest, PlanResponse } from "../contracts/types";
import { PlanSection } from "./PlanSection";

const REQUEST: ItineraryRequest = {
  destination: { name: "Goa" },
  start_date: "2026-11-07",
  days: 2,
  travellers: 2,
  preferences: null,
};

function response(source: PlanResponse["source"], notice = "Server notice."): PlanResponse {
  return {
    source,
    notice,
    plan: {
      days: [
        { day_number: 1, items: [{ title: "Arrive and settle in", description: null }] },
        {
          day_number: 2,
          items: [
            { title: "Explore the old quarter", description: "A relaxed walk." },
            { title: "Local lunch", description: null },
          ],
        },
      ],
      notes: "Check everything before you go.",
    },
  };
}

describe("PlanSection", () => {
  test("shows a progress message while the server is writing", () => {
    const load = vi.fn().mockReturnValue(new Promise(() => undefined));
    render(<PlanSection request={REQUEST} load={load} />);

    expect(screen.getByRole("status")).toHaveTextContent("Writing your plan");
    expect(screen.getByRole("heading", { name: "2-day plan for Goa" })).toBeInTheDocument();
  });

  test("asks the server for exactly the request it was given", async () => {
    const load = vi.fn().mockResolvedValue(response("SCRIPTED_SAMPLE"));
    render(<PlanSection request={REQUEST} load={load} />);

    await screen.findByText("Arrive and settle in");

    expect(load).toHaveBeenCalledTimes(1);
    expect(load.mock.calls[0]?.[0]).toEqual(REQUEST);
  });

  test("a scripted sample is labelled as one, on the banner and on every line", async () => {
    render(<PlanSection request={REQUEST} load={vi.fn().mockResolvedValue(response("SCRIPTED_SAMPLE"))} />);

    await screen.findByText("Arrive and settle in");

    expect(screen.getByText(/not written by a language model/i)).toBeInTheDocument();
    expect(screen.getByText(/Server notice\./)).toBeInTheDocument();
    expect(screen.getAllByText("Scripted sample")).toHaveLength(3);
    expect(screen.queryByText(/AI suggestion/)).not.toBeInTheDocument();
  });

  test("a model's plan is labelled an AI suggestion, not verified, and never as a sample", async () => {
    render(<PlanSection request={REQUEST} load={vi.fn().mockResolvedValue(response("AI_SUGGESTION"))} />);

    await screen.findByText("Explore the old quarter");

    expect(screen.getAllByText("AI suggestion, not verified")).toHaveLength(3);
    expect(screen.getByText("AI suggestion · not verified")).toBeInTheDocument();
    expect(screen.queryByText(/Scripted sample/)).not.toBeInTheDocument();
    expect(screen.getByText("A relaxed walk.")).toBeInTheDocument();
    expect(screen.getByText("Check everything before you go.")).toBeInTheDocument();
  });

  test("works out each calendar date from the start date", async () => {
    render(<PlanSection request={REQUEST} load={vi.fn().mockResolvedValue(response("SCRIPTED_SAMPLE"))} />);

    expect(await screen.findByRole("heading", { level: 3, name: /Day 1.*Sat, 7 Nov/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /Day 2.*Sun, 8 Nov/ })).toBeInTheDocument();
    expect(screen.getByText(/2 travellers/)).toBeInTheDocument();
  });

  test("offers nothing to book, approve or pay", async () => {
    render(<PlanSection request={REQUEST} load={vi.fn().mockResolvedValue(response("AI_SUGGESTION"))} />);

    await screen.findByText("Local lunch");

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing here can be booked/)).toBeInTheDocument();
  });

  test("when the server fails it says so and shows no plan at all", async () => {
    const load = vi.fn().mockRejectedValue(new ChatApiError(503, "The model service is not available right now."));
    render(<PlanSection request={REQUEST} load={load} />);

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent("The plan could not be written.");
    expect(alert).toHaveTextContent("The model service is not available right now.");
    expect(screen.queryByText("Arrive and settle in")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  test("an unreachable server is reported and a retry asks again", async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new ChatApiError(null, null))
      .mockResolvedValueOnce(response("SCRIPTED_SAMPLE"));
    render(<PlanSection request={REQUEST} load={load} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be reached/i);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Arrive and settle in")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("a new request replaces the old plan and asks again", async () => {
    const load = vi.fn().mockResolvedValue(response("SCRIPTED_SAMPLE"));
    const { rerender } = render(<PlanSection request={REQUEST} load={load} />);
    await screen.findByText("Arrive and settle in");

    rerender(<PlanSection request={{ ...REQUEST, days: 3, destination: { name: "Pune" } }} load={load} />);

    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(load.mock.calls[1]?.[0]).toMatchObject({ days: 3, destination: { name: "Pune" } });
    expect(await screen.findByRole("heading", { name: "3-day plan for Pune" })).toBeInTheDocument();
  });

  test("a late answer for an old request is ignored", async () => {
    let resolveFirst: (value: PlanResponse) => void = () => undefined;
    const load = vi
      .fn()
      .mockReturnValueOnce(new Promise<PlanResponse>((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce({ ...response("SCRIPTED_SAMPLE"), notice: "Second answer." });
    const { rerender } = render(<PlanSection request={REQUEST} load={load} />);

    rerender(<PlanSection request={{ ...REQUEST, days: 3 }} load={load} />);
    await screen.findByText(/Second answer\./);
    resolveFirst({ ...response("AI_SUGGESTION"), notice: "First answer." });
    await Promise.resolve();

    expect(screen.queryByText(/First answer\./)).not.toBeInTheDocument();
    expect(screen.getByText(/Second answer\./)).toBeInTheDocument();
  });
});
