import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { PlanningRun } from "../api/planning";
import { ServerClarification } from "./ServerClarification";

const RUN: PlanningRun = {
  runId: "r1",
  tripId: "t1",
  status: "awaiting_clarification",
  choices: null,
  research: null,
  estimate: null,
  error: null,
  questions: ["How many travellers are going?"],
  selected: null,
  itinerary: null,
  itineraryWarnings: [],
  weather: null,
  providerIssues: [],
  notes: [],
};

const DRAFT = {
  origin: "Indore",
  destination: "Goa",
  trip_type: "ONE_WAY",
  departure_date: "2026-12-12",
  return_date: null,
  traveller_count: null,
  preferences: null,
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("clarification", () => {
  test("shows the server's questions and the draft as the server holds it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(() => Promise.resolve(json({ id: "t1", draft: DRAFT }))),
    );
    render(<ServerClarification run={RUN} onAnswered={() => undefined} />);

    expect(screen.getByText("How many travellers are going?")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Indore")).toBeInTheDocument();
    expect((screen.getByLabelText("Travellers") as HTMLInputElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Send these details" })).toBeEnabled();
  });

  test("sends the whole draft with the traveller's answer and hands back the resumed run", async () => {
    const resumed = { run_id: "r1", trip_id: "t1", status: "running", waiting_for: null, research: null, summary: null, error: null };
    const spy = vi.fn<typeof fetch>((_input, init) =>
      Promise.resolve(init?.method === "POST" ? json(resumed, 202) : json({ id: "t1", draft: DRAFT })),
    );
    vi.stubGlobal("fetch", spy);
    const onAnswered = vi.fn();
    render(<ServerClarification run={RUN} onAnswered={onAnswered} />);
    await screen.findByDisplayValue("Indore");

    fireEvent.change(screen.getByLabelText("Travellers"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Send these details" }));

    await vi.waitFor(() => expect(onAnswered).toHaveBeenCalledTimes(1));
    const post = spy.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(post?.[0])).toMatch(/\/api\/v1\/runs\/r1\/clarifications$/);
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      draft: { ...DRAFT, traveller_count: 2 },
    });
  });

  test("a refused answer shows the server's wording", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((_input, init) =>
        Promise.resolve(
          init?.method === "POST"
            ? json({ title: "Conflict", detail: "That run is not waiting for an answer." }, 409)
            : json({ id: "t1", draft: DRAFT }),
        ),
      ),
    );
    render(<ServerClarification run={RUN} onAnswered={() => undefined} />);
    await screen.findByDisplayValue("Indore");

    fireEvent.click(screen.getByRole("button", { name: "Send these details" }));

    expect(await screen.findByText("That run is not waiting for an answer.")).toBeInTheDocument();
  });
});
