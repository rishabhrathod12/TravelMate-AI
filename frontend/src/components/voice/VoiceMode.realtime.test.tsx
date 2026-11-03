import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { createRealtimeAdapter, REALTIME_DISCLOSURE } from "../../voice/realtimeAdapter";
import { VoiceMode } from "./VoiceMode";

describe("live voice on the voice screen (ADR 0008)", () => {
  test("says where the audio goes before any session is opened, and links it to the button", () => {
    render(<VoiceMode adapter={createRealtimeAdapter()} />);

    const start = screen.getByRole("button", { name: "Talk to TravelMate" });
    const disclosure = screen.getByText(REALTIME_DISCLOSURE);

    expect(disclosure).toHaveTextContent(/microphone audio is sent to OpenAI/);
    expect(disclosure).toHaveTextContent(/cannot search, book or approve/);
    expect(start.getAttribute("aria-describedby")).toBe(disclosure.id);
  });

  test("opens no session and asks for no microphone just by being shown", () => {
    render(<VoiceMode adapter={createRealtimeAdapter()} />);

    expect(screen.getByRole("button", { name: "Talk to TravelMate" })).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("it is never presented as the scripted voice", () => {
    render(<VoiceMode adapter={createRealtimeAdapter()} />);

    expect(screen.queryByText(/Scripted voice/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Simulate:/)).not.toBeInTheDocument();
  });
});
