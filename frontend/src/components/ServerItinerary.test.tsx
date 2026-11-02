import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { Itinerary } from "../contracts/types";
import { ServerItinerary } from "./ServerItinerary";

const DRAFT: Itinerary = {
  days: [
    {
      day_number: 1,
      items: [
        { title: "Travel to Goa", description: null, option_id: "a" },
        { title: "Beach walk", description: "Evening", option_id: null },
      ],
    },
    { day_number: 2, items: [] },
  ],
  notes: null,
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("the itinerary draft", () => {
  test("is labelled as an unverified draft and saving is off until something changes", () => {
    render(<ServerItinerary tripId="t1" initial={DRAFT} warnings={["Day 3 was left empty."]} />);

    expect(screen.getByRole("heading", { name: "Itinerary draft (not verified)" })).toBeInTheDocument();
    expect(screen.getByText("Day 3 was left empty.")).toBeInTheDocument();
    expect(screen.getByText("Refers to a chosen option.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save as a new version" })).toBeDisabled();
  });

  test("edited text is saved as a new version and the option reference is kept", async () => {
    const spy = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        json({ trip_id: "t1", version: 2, created_by: "user", itinerary: DRAFT, created_at: "x", request_id: "r" }, 201),
      ),
    );
    vi.stubGlobal("fetch", spy);
    render(<ServerItinerary tripId="t1" initial={DRAFT} warnings={[]} />);

    fireEvent.change(screen.getByLabelText("Day 1 item 1 title"), { target: { value: "Fly to Goa" } });
    fireEvent.click(screen.getByRole("button", { name: "Remove item 2 of day 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Add an item to day 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Save as a new version" }));

    expect(await screen.findByText("Saved as version 2")).toBeInTheDocument();
    const [url, init] = spy.mock.calls[0] ?? [];
    expect(String(url)).toMatch(/\/api\/v1\/trips\/t1\/itinerary\/versions$/);
    expect(init?.method).toBe("POST");
    const sent = JSON.parse(String(init?.body)) as { itinerary: Itinerary };
    expect(sent.itinerary.days[0]?.items).toEqual([{ title: "Fly to Goa", description: null, option_id: "a" }]);
    expect(sent.itinerary.days[1]?.items).toHaveLength(1);
  });

  test("an empty title cannot be saved", () => {
    render(<ServerItinerary tripId="t1" initial={DRAFT} warnings={[]} />);

    fireEvent.change(screen.getByLabelText("Day 1 item 2 title"), { target: { value: "  " } });

    expect(screen.getByRole("button", { name: "Save as a new version" })).toBeDisabled();
  });

  test("a refused save shows the server's wording and keeps the edits", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(() =>
        Promise.resolve(json({ title: "Unprocessable", detail: "That itinerary refers to an unknown option." }, 422)),
      ),
    );
    render(<ServerItinerary tripId="t1" initial={DRAFT} warnings={[]} />);
    fireEvent.change(screen.getByLabelText("Day 1 item 2 title"), { target: { value: "Dinner" } });

    fireEvent.click(screen.getByRole("button", { name: "Save as a new version" }));

    expect(await screen.findByText("That itinerary refers to an unknown option.")).toBeInTheDocument();
    expect((screen.getByLabelText("Day 1 item 2 title") as HTMLInputElement).value).toBe("Dinner");
  });
});
