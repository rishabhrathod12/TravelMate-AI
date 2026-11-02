import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { useFollowBottom } from "./useFollowBottom";

/**
 * jsdom has no layout, so scrolling, the size observer and the end element's position are stubbed.
 * The viewport is 768 px tall in jsdom: the end of the conversation counts as "near the bottom"
 * while it is at most 80 px below that line (so a `bottom` of 848 or less), and as far away above it.
 */
const NEAR = 700;
const FAR = 2000;

function Harness({ count, fromUser }: { count: number; fromUser: boolean }) {
  const { contentRef, endRef } = useFollowBottom({ messageCount: count, lastFromUser: fromUser });
  return (
    <div ref={contentRef} data-testid="content">
      <div ref={endRef} data-testid="end" />
    </div>
  );
}

/** Reports the new height of the observed element, as the real observer does. */
class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  static height = 0;
  disconnect = vi.fn();
  observe = vi.fn();
  constructor(private readonly callback: (entries: ResizeObserverEntry[]) => void) {
    FakeResizeObserver.instances.push(this);
  }
  /** The conversation grows (or, if negative, shrinks) by `by` pixels. */
  fire(by = 100) {
    FakeResizeObserver.height += by;
    this.callback([{ contentRect: { height: FakeResizeObserver.height } } as ResizeObserverEntry]);
  }
}

let scrollSpy: ReturnType<typeof vi.fn>;
let now = 1000;
// Like a browser, animation frames run later, not at once.
let frames: { id: number; callback: FrameRequestCallback }[] = [];
let nextFrame = 1;

function flushFrames() {
  const due = frames;
  frames = [];
  for (const frame of due) {
    frame.callback(0);
  }
}

function placeEnd(bottom: number) {
  const end = screen.getByTestId("end");
  end.getBoundingClientRect = () => ({ bottom }) as DOMRect;
}

/** The reader scrolls: the page tells the hook, which works out where they are. */
function readerScrolls(bottom: number) {
  placeEnd(bottom);
  act(() => {
    fireEvent.scroll(window);
  });
}

function contentGrows(by = 100) {
  act(() => {
    FakeResizeObserver.instances.at(-1)?.fire(by);
    flushFrames();
  });
}

function reducedMotion(on: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({ matches: on && query.includes("reduce"), addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

beforeEach(() => {
  now = 1000;
  scrollSpy = vi.fn();
  Element.prototype.scrollIntoView = scrollSpy as unknown as typeof Element.prototype.scrollIntoView;
  FakeResizeObserver.instances = [];
  FakeResizeObserver.height = 0;
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  frames = [];
  nextFrame = 1;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    const id = nextFrame++;
    frames.push({ id, callback });
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    frames = frames.filter((frame) => frame.id !== id);
  });
  vi.spyOn(performance, "now").mockImplementation(() => now);
  reducedMotion(false);
});

afterEach(() => {
  delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  vi.restoreAllMocks();
});

describe("sending a message", () => {
  test("scrolls to it, smoothly, and stops short of the composer's room", () => {
    const { rerender } = render(<Harness count={0} fromUser={false} />);
    expect(scrollSpy).not.toHaveBeenCalled();

    rerender(<Harness count={1} fromUser />);

    expect(scrollSpy).toHaveBeenCalledTimes(1);
    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "smooth" });
  });

  test("uses an instant scroll when the reader prefers reduced motion", () => {
    reducedMotion(true);
    const { rerender } = render(<Harness count={0} fromUser={false} />);

    rerender(<Harness count={1} fromUser />);

    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "auto" });
  });

  test("scrolls even when the reader had scrolled up to read", () => {
    const { rerender } = render(<Harness count={1} fromUser />);
    scrollSpy.mockClear();
    now += 5000; // the first smooth scroll is long over
    readerScrolls(FAR);

    rerender(<Harness count={3} fromUser />);

    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "smooth" });
  });
});

describe("content that grows (a reply, an error, a plan that loads, text arriving)", () => {
  test("is followed while the reader is at the bottom, with an instant scroll", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(NEAR);

    contentGrows();

    expect(scrollSpy).toHaveBeenCalledTimes(1);
    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "auto" });
  });

  test("many size changes within one frame cause one scroll", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(NEAR);

    act(() => {
      const observer = FakeResizeObserver.instances.at(-1);
      observer?.fire(100);
      observer?.fire(100);
      observer?.fire(100);
      flushFrames();
    });

    expect(scrollSpy).toHaveBeenCalledTimes(1);
  });

  test("a panel taller than the screen is not followed to its far end", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(NEAR);

    contentGrows(5000); // the comparison view appears: thousands of pixels in one step

    expect(scrollSpy).not.toHaveBeenCalled();
  });

  test("growth up to a screen is still a message and is followed", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(NEAR);

    contentGrows(700);

    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "auto" });
  });

  test("after a big panel the next message-sized growth is followed again", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(NEAR);
    contentGrows(5000);
    expect(scrollSpy).not.toHaveBeenCalled();

    contentGrows(100);

    expect(scrollSpy).toHaveBeenCalledTimes(1);
  });

  test("a conversation that gets shorter never scrolls", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(NEAR);

    contentGrows(-300);

    expect(scrollSpy).not.toHaveBeenCalled();
  });

  test("is not followed once the reader has scrolled up", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(FAR);

    contentGrows();
    contentGrows();

    expect(scrollSpy).not.toHaveBeenCalled();
  });

  test("is followed again when the reader comes back near the bottom", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(FAR);
    contentGrows();
    expect(scrollSpy).not.toHaveBeenCalled();

    readerScrolls(NEAR + 100); // within 80 px of the line: close enough
    contentGrows();

    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "auto" });
  });

  test("a reader a long way above the bottom stays put", () => {
    render(<Harness count={2} fromUser={false} />);
    readerScrolls(768 + 81); // one pixel too far

    contentGrows();

    expect(scrollSpy).not.toHaveBeenCalled();
  });

  test("scroll events of our own smooth scroll are not mistaken for the reader leaving", () => {
    const { rerender } = render(<Harness count={0} fromUser={false} />);
    rerender(<Harness count={1} fromUser />); // starts a smooth scroll
    scrollSpy.mockClear();

    readerScrolls(FAR); // an event on the way, while the smooth scroll is still running
    now += 1000; // it has finished
    contentGrows();

    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "auto" });
  });

  test("growth during a smooth scroll retargets it, smoothly, instead of jumping or waiting", () => {
    const { rerender } = render(<Harness count={0} fromUser={false} />);
    rerender(<Harness count={1} fromUser />);
    scrollSpy.mockClear();

    contentGrows(); // a reply arrives while the smooth scroll to the sent message still runs

    expect(scrollSpy).toHaveBeenCalledTimes(1);
    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "smooth" });
  });
});

describe("unrelated renders", () => {
  test("do not scroll", () => {
    const { rerender } = render(<Harness count={2} fromUser={false} />);
    scrollSpy.mockClear();

    rerender(<Harness count={2} fromUser={false} />);
    rerender(<Harness count={2} fromUser={false} />);

    expect(scrollSpy).not.toHaveBeenCalled();
  });

  test("a reply that is only a rerender of the same count does not scroll the reader down", () => {
    const { rerender } = render(<Harness count={4} fromUser />);
    scrollSpy.mockClear();
    now += 5000;
    readerScrolls(FAR);

    rerender(<Harness count={4} fromUser />);

    expect(scrollSpy).not.toHaveBeenCalled();
  });
});

describe("clean-up and fallback", () => {
  test("removes the scroll listener and disconnects the observer on unmount", () => {
    const removed = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<Harness count={1} fromUser />);
    const observer = FakeResizeObserver.instances.at(-1);

    unmount();

    expect(removed).toHaveBeenCalledWith("scroll", expect.any(Function));
    expect(observer?.disconnect).toHaveBeenCalledTimes(1);
  });

  test("without a size observer a reply still scrolls while the reader is at the bottom", () => {
    vi.stubGlobal("ResizeObserver", undefined);
    const { rerender } = render(<Harness count={1} fromUser />);
    scrollSpy.mockClear();

    rerender(<Harness count={2} fromUser={false} />);

    expect(scrollSpy).toHaveBeenCalledWith({ block: "end", behavior: "auto" });
  });

  test("without a size observer a reader who scrolled up is still left alone", () => {
    vi.stubGlobal("ResizeObserver", undefined);
    const { rerender } = render(<Harness count={1} fromUser />);
    now += 5000;
    readerScrolls(FAR);
    scrollSpy.mockClear();

    rerender(<Harness count={2} fromUser={false} />);

    expect(scrollSpy).not.toHaveBeenCalled();
  });
});
