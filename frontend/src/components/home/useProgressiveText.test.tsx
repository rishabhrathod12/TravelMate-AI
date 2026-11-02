import { act, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { useProgressiveText } from "./useProgressiveText";

let skipHandle: (() => void) | null = null;

function Probe({ text, enabled }: { text: string; enabled: boolean }) {
  const { shown, done, skip } = useProgressiveText(text, enabled);
  useEffect(() => {
    skipHandle = skip;
  }, [skip]);
  return (
    <div>
      <span data-testid="shown">{shown}</span>
      <span data-testid="done">{String(done)}</span>
    </div>
  );
}

const shown = () => screen.getByTestId("shown").textContent ?? "";
const isDone = () => screen.getByTestId("done").textContent === "true";

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

function reducedMotion(on: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({ matches: on && query.includes("reduce"), addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

const SENTENCE = "Which dates would you like to travel, and how many people are going?";

beforeEach(() => {
  vi.useFakeTimers();
  reducedMotion(false);
  skipHandle = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("revealing text", () => {
  test("starts empty, grows as a prefix of the text, and ends with all of it", () => {
    render(<Probe text={SENTENCE} enabled />);
    expect(shown()).toBe("");
    expect(isDone()).toBe(false);

    let previousLength = 0;
    for (let tick = 0; tick < 200 && !isDone(); tick += 1) {
      advance(30);
      expect(SENTENCE.startsWith(shown())).toBe(true);
      expect(shown().length).toBeGreaterThanOrEqual(previousLength);
      previousLength = shown().length;
    }

    expect(shown()).toBe(SENTENCE);
    expect(isDone()).toBe(true);
  });

  test("a short reply takes about a second, not instantly and not slowly", () => {
    render(<Probe text={SENTENCE} enabled />);

    advance(300);
    expect(isDone()).toBe(false);
    advance(1500);
    expect(isDone()).toBe(true);
  });

  test("however long the text, it is all shown within two seconds", () => {
    const long = "word ".repeat(2000);
    render(<Probe text={long} enabled />);

    advance(2100);

    expect(isDone()).toBe(true);
    expect(shown()).toBe(long);
  });

  test("never splits a character made of two code units", () => {
    const text = "Beach 🏖️ day 😀 then home";
    render(<Probe text={text} enabled />);

    for (let tick = 0; tick < 100 && !isDone(); tick += 1) {
      advance(30);
      expect(shown()).not.toMatch(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/);
    }
    expect(shown()).toBe(text);
  });

  test("stops its timer when it finishes", () => {
    render(<Probe text="Hi there" enabled />);

    advance(2100);

    expect(isDone()).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("stops its timer when it is removed part-way", () => {
    const { unmount } = render(<Probe text={SENTENCE} enabled />);
    advance(60);
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("showing everything at once", () => {
  test("when it is not enabled", () => {
    render(<Probe text={SENTENCE} enabled={false} />);

    expect(shown()).toBe(SENTENCE);
    expect(isDone()).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("when the reader prefers reduced motion", () => {
    reducedMotion(true);
    render(<Probe text={SENTENCE} enabled />);

    expect(shown()).toBe(SENTENCE);
    expect(isDone()).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("when skipped part-way", () => {
    render(<Probe text={SENTENCE} enabled />);
    advance(90);
    expect(isDone()).toBe(false);

    act(() => skipHandle?.());

    expect(shown()).toBe(SENTENCE);
    expect(isDone()).toBe(true);
  });

  test("when it stops being enabled part-way", () => {
    const { rerender } = render(<Probe text={SENTENCE} enabled />);
    advance(90);

    rerender(<Probe text={SENTENCE} enabled={false} />);

    expect(shown()).toBe(SENTENCE);
    expect(isDone()).toBe(true);
  });
});

describe("text that keeps growing (a real stream, if one ever exists)", () => {
  test("continues where it was instead of starting again", () => {
    const { rerender } = render(<Probe text="Hello there, " enabled />);
    advance(150);
    const before = shown();
    expect(before.length).toBeGreaterThan(0);

    rerender(<Probe text="Hello there, and welcome to the trip." enabled />);

    expect(shown().startsWith(before)).toBe(true);
    expect(shown().length).toBeGreaterThanOrEqual(before.length);
    advance(2100);
    expect(shown()).toBe("Hello there, and welcome to the trip.");
  });

  test("different text, not a continuation, starts again from the beginning", () => {
    const { rerender } = render(<Probe text="Hello there, friend" enabled />);
    advance(200);
    expect(shown().length).toBeGreaterThan(0);

    rerender(<Probe text="Something else entirely" enabled />);

    expect(shown()).toBe("");
    advance(2100);
    expect(shown()).toBe("Something else entirely");
  });
});
