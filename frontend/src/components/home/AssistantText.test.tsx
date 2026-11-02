import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { AssistantText } from "./AssistantText";

const REPLY = "## Your plan\n\n- Day 1: **beach**\n- Day 2: see [the docs](https://example.com/guide)\n\nEnjoy the trip.";

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

beforeEach(() => {
  vi.useFakeTimers();
  reducedMotion(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("while a reply is revealed", () => {
  test("the animated text is hidden from assistive technology and links are not focusable", () => {
    const { container } = render(<AssistantText text={REPLY} reveal />);

    const stack = container.querySelector(".reveal-stack");
    expect(stack?.getAttribute("aria-hidden")).toBe("true");
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelectorAll(".reveal-stack [tabindex]")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Show the whole reply" })).toBeInTheDocument();
  });

  test("the bubble has its final size from the start: the full text sits invisibly under the visible part", () => {
    const { container } = render(<AssistantText text={REPLY} reveal />);

    expect(container.querySelector(".reveal-full")?.textContent).toContain("Enjoy the trip.");
    expect(container.querySelector(".reveal-visible")?.textContent).toBe("");
    advance(200);
    expect((container.querySelector(".reveal-visible")?.textContent ?? "").length).toBeGreaterThan(0);
    expect(container.querySelector(".reveal-full")?.textContent).toContain("Enjoy the trip.");
  });

  test("when it finishes, the finished reply replaces it, with real headings, lists and links", () => {
    const { container } = render(<AssistantText text={REPLY} reveal />);

    advance(2100);

    expect(container.querySelector(".reveal-stack")).toBeNull();
    expect(screen.queryByRole("button", { name: "Show the whole reply" })).not.toBeInTheDocument();
    // The shallowest heading becomes an h2 whatever it was written as: the page owns the h1.
    expect(container.querySelector("h2")?.textContent).toBe("Your plan");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("strong")?.textContent).toBe("beach");
    expect(container.querySelector("a")?.getAttribute("href")).toBe("https://example.com/guide");
  });

  test("the reply text exists once when finished, never twice", () => {
    render(<AssistantText text="Which dates would you like?" reveal />);

    advance(2100);

    expect(screen.getAllByText("Which dates would you like?")).toHaveLength(1);
  });
});

describe("skipping", () => {
  test("the button shows everything at once", () => {
    const { container } = render(<AssistantText text={REPLY} reveal />);
    advance(60);

    fireEvent.click(screen.getByRole("button", { name: "Show the whole reply" }));

    expect(container.querySelector(".reveal-stack")).toBeNull();
    expect(container.textContent).toContain("Enjoy the trip.");
    expect(screen.queryByRole("button", { name: "Show the whole reply" })).not.toBeInTheDocument();
  });

  test("Escape shows everything at once", () => {
    const { container } = render(<AssistantText text={REPLY} reveal />);
    advance(60);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(container.querySelector(".reveal-stack")).toBeNull();
    expect(container.textContent).toContain("Enjoy the trip.");
  });

  test("a keyboard user who skipped does not lose their place: focus moves on", () => {
    const target = document.createElement("textarea");
    document.body.append(target);
    render(<AssistantText text={REPLY} reveal focusAfterSkip={() => target} />);
    screen.getByRole("button", { name: "Show the whole reply" }).focus();

    fireEvent.click(screen.getByRole("button", { name: "Show the whole reply" }));
    advance(10);

    expect(document.activeElement).toBe(target);
    target.remove();
  });

  test("a mouse user's focus is left alone", () => {
    const target = document.createElement("textarea");
    document.body.append(target);
    render(<AssistantText text={REPLY} reveal focusAfterSkip={() => target} />);

    fireEvent.click(screen.getByRole("button", { name: "Show the whole reply" }));
    advance(10);

    expect(document.activeElement).not.toBe(target);
    target.remove();
  });

  test("Escape does nothing once the reply is whole", () => {
    const removed = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<AssistantText text="Hi" reveal />);
    advance(2100);

    fireEvent.keyDown(document, { key: "Escape" });
    unmount();

    expect(removed).toHaveBeenCalledWith("keydown", expect.any(Function));
  });
});

describe("a reply that is not revealed", () => {
  test("an older reply, or one after the reader wrote again, is whole at once", () => {
    const { container } = render(<AssistantText text={REPLY} reveal={false} />);

    expect(container.querySelector(".reveal-stack")).toBeNull();
    expect(screen.queryByRole("button", { name: "Show the whole reply" })).not.toBeInTheDocument();
    expect(container.textContent).toContain("Enjoy the trip.");
    expect(vi.getTimerCount()).toBe(0);
  });

  test("a reply being revealed becomes whole at once when the reader writes again", () => {
    const { container, rerender } = render(<AssistantText text={REPLY} reveal />);
    advance(60);

    rerender(<AssistantText text={REPLY} reveal={false} />);

    expect(container.querySelector(".reveal-stack")).toBeNull();
    expect(container.textContent).toContain("Enjoy the trip.");
    expect(vi.getTimerCount()).toBe(0);
  });

  test("reduced motion shows the whole reply at once", () => {
    reducedMotion(true);
    const { container } = render(<AssistantText text={REPLY} reveal />);

    expect(container.querySelector(".reveal-stack")).toBeNull();
    expect(screen.queryByRole("button", { name: "Show the whole reply" })).not.toBeInTheDocument();
    expect(container.textContent).toContain("Enjoy the trip.");
  });
});

describe("text nobody has vouched for", () => {
  test("raw HTML in a reply is text, before, during and after the reveal", () => {
    const hostile = '<img src=x onerror="alert(1)"> and [x](javascript:alert(1))';
    const { container } = render(<AssistantText text={hostile} reveal />);

    expect(container.querySelector("img")).toBeNull();
    advance(100);
    expect(container.querySelector("img")).toBeNull();
    advance(2100);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });
});
