import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { TranscriptSource } from "../../voice/VoiceAdapter";
import type { TranscriptEntry } from "../../voice/voiceMachine";
import { VoiceTranscript } from "./VoiceTranscript";

/** jsdom has no layout: the box is 200 px tall and its content grows 60 px per entry. */
const BOX = 200;
let now = 1000;
let scrollTop = 0;
let scrollToSpy: ReturnType<typeof vi.fn>;
let entryCount = 0;

function entries(spec: [("user" | "assistant"), TranscriptSource][]): TranscriptEntry[] {
  return spec.map(([speaker, source], index) => ({ id: index + 1, speaker, text: `line ${index + 1}`, source }));
}

function ui(spec: [("user" | "assistant"), TranscriptSource][]) {
  entryCount = spec.length;
  return <VoiceTranscript entries={entries(spec)} />;
}

beforeEach(() => {
  now = 1000;
  scrollTop = 0;
  vi.spyOn(performance, "now").mockImplementation(() => now);
  scrollToSpy = vi.fn((options: ScrollToOptions) => {
    scrollTop = Math.max(0, Number(options.top) - BOX);
  });
  Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: scrollToSpy });
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => BOX + entryCount * 60 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => BOX });
  Object.defineProperty(HTMLElement.prototype, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = value;
    },
  });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function readerScrollsUp() {
  now += 5000;
  scrollTop = 0;
  act(() => {
    fireEvent.scroll(screen.getByRole("log"));
  });
  scrollToSpy.mockClear();
}

describe("the voice transcript follows its newest entry inside its own box", () => {
  test("a reply from the assistant scrolls the box to the end", () => {
    const view = render(ui([["user", "voice"]]));

    view.rerender(ui([["user", "voice"], ["assistant", "assistant"]]));

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: BOX + 2 * 60, behavior: "auto" });
  });

  test("what the reader says aloud does not pull them back down once they have scrolled up", () => {
    const view = render(ui([["assistant", "assistant"], ["user", "voice"], ["assistant", "assistant"]]));
    readerScrollsUp();

    view.rerender(ui([["assistant", "assistant"], ["user", "voice"], ["assistant", "assistant"], ["user", "voice"]]));

    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  test("a message the reader types always scrolls to it, smoothly", () => {
    const view = render(ui([["assistant", "assistant"], ["user", "voice"], ["assistant", "assistant"]]));
    readerScrollsUp();

    view.rerender(ui([["assistant", "assistant"], ["user", "voice"], ["assistant", "assistant"], ["user", "typed"]]));

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: BOX + 4 * 60, behavior: "smooth" });
  });

  test("the assistant's reply to that typed message is followed too", () => {
    const base: [("user" | "assistant"), TranscriptSource][] = [["assistant", "assistant"], ["user", "voice"], ["assistant", "assistant"]];
    const view = render(ui(base));
    readerScrollsUp();
    view.rerender(ui([...base, ["user", "typed"]]));
    scrollToSpy.mockClear();

    view.rerender(ui([...base, ["user", "typed"], ["assistant", "assistant"]]));

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: BOX + 5 * 60, behavior: "auto" });
  });

  test("it renders nothing, and attaches no scrolling, with no entries", () => {
    render(ui([]));

    expect(screen.queryByRole("log")).not.toBeInTheDocument();
    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  test("the box keeps its accessible name, polite log role and keyboard focus", () => {
    render(ui([["user", "voice"]]));

    const log = screen.getByRole("log", { name: "Transcript" });
    expect(log).toHaveAttribute("tabindex", "0");
  });
});
