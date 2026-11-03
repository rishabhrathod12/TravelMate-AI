import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { ChatApiError, type ChatTurn } from "../api/chat";
import type { TripRequest } from "../contracts/types";
import { TripChat } from "./TripChat";

const REQUEST: TripRequest = {
  trip_type: "ONE_WAY",
  origin: { name: "Indore" },
  destination: { name: "Goa" },
  departure_date: "2026-12-12",
  return_date: null,
  travellers: [{ age: null }],
  preferences: null,
};

function turn(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    status: "NEEDS_INFO",
    reply: "Which date do you want to leave?",
    draft: { origin: "Indore", destination: "Goa" },
    tripRequest: null,
    itineraryRequest: null,
    modelKind: "DEV_STAND_IN",
    modelNotice: "Development stand-in: not a language model.",
    ...overrides,
  };
}

const typeAndSend = (message: string) => {
  fireEvent.change(screen.getByLabelText(/for example/i), { target: { value: message } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
};

describe("TripChat", () => {
  test("before any reply it claims nothing about who reads the message", () => {
    render(<TripChat onUseRequest={vi.fn()} />);

    expect(screen.getByText(/reads the details you state/i)).toBeInTheDocument();
    expect(screen.queryByText(/not a language model/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no model is connected/i)).not.toBeInTheDocument();
  });

  test("after a reply it shows the server's own wording about who read it: the stand-in", async () => {
    render(<TripChat onUseRequest={vi.fn()} send={vi.fn().mockResolvedValue(turn())} />);

    typeAndSend("Indore to Goa");

    expect(await screen.findByText(/Development stand-in: not a language model/)).toBeInTheDocument();
  });

  test("and when an OpenAI model read it, it says so and does not call it a stand-in", async () => {
    const live = turn({
      modelKind: "OPENAI",
      modelNotice: "An OpenAI language model reads your messages. Your text is sent to OpenAI.",
    });
    render(<TripChat onUseRequest={vi.fn()} send={vi.fn().mockResolvedValue(live)} />);

    typeAndSend("Indore to Goa");

    expect(await screen.findByText(/Your text is sent to OpenAI/)).toBeInTheDocument();
    expect(screen.queryByText(/Development stand-in/)).not.toBeInTheDocument();
  });

  test("shows what was typed and the reply, and sends the draft back on the next turn", async () => {
    const send = vi.fn().mockResolvedValueOnce(turn()).mockResolvedValueOnce(turn());
    render(<TripChat onUseRequest={vi.fn()} send={send} />);

    typeAndSend("Indore to Goa");
    expect(await screen.findByText("Which date do you want to leave?")).toBeInTheDocument();
    expect(screen.getByText("Indore to Goa")).toBeInTheDocument();
    expect(send.mock.calls[0]?.[1]).toBeNull();

    typeAndSend("12 December 2026");
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls[1]?.[1]).toEqual({ origin: "Indore", destination: "Goa" });
  });

  test("offers the details only when the server says they are ready", async () => {
    const onUseRequest = vi.fn();
    const send = vi
      .fn()
      .mockResolvedValueOnce(turn())
      .mockResolvedValueOnce(
        turn({ status: "READY_FOR_REVIEW", tripRequest: REQUEST, reply: "Here is what I have." }),
      );
    render(<TripChat onUseRequest={onUseRequest} send={send} />);

    typeAndSend("Indore to Goa");
    await screen.findByText("Which date do you want to leave?");
    expect(screen.queryByRole("button", { name: "Use these details" })).not.toBeInTheDocument();

    typeAndSend("12 December 2026");
    fireEvent.click(await screen.findByRole("button", { name: "Use these details" }));

    expect(onUseRequest).toHaveBeenCalledWith(REQUEST);
    expect(screen.getByText(/nothing is booked/i)).toBeInTheDocument();
  });

  test("a missing endpoint explains how to switch chat on", async () => {
    const send = vi.fn().mockRejectedValue(new ChatApiError(404, null));
    render(<TripChat onUseRequest={vi.fn()} send={send} />);

    typeAndSend("hi");

    expect(await screen.findByRole("alert")).toHaveTextContent(/CONVERSATION_ENABLED/);
  });

  test("an unreachable server is reported", async () => {
    const send = vi.fn().mockRejectedValue(new ChatApiError(null, null));
    render(<TripChat onUseRequest={vi.fn()} send={send} />);

    typeAndSend("hi");

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be reached/i);
  });

  test("start over clears the conversation and the draft", async () => {
    const send = vi.fn().mockResolvedValue(turn());
    render(<TripChat onUseRequest={vi.fn()} send={send} />);
    typeAndSend("Indore to Goa");
    await screen.findByText("Which date do you want to leave?");

    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.queryByText("Which date do you want to leave?")).not.toBeInTheDocument();

    typeAndSend("Pune to Goa");
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls[1]?.[1]).toBeNull();
  });

  test("an empty message is not sent", () => {
    const send = vi.fn();
    render(<TripChat onUseRequest={vi.fn()} send={send} />);

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(send).not.toHaveBeenCalled();
  });
});
