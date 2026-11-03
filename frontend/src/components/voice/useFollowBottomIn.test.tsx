import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { useFollowBottomIn } from "./useFollowBottomIn";

/**
 * jsdom has no layout, so the box's size, its scroll position and the size observer are stubbed.
 * The box is 200 px tall; the reader counts as "at the bottom" while the end is at most 48 px
 * below the visible area.
 */
const BOX = 200;

/** `fromUser` here means "the reader typed and sent this entry" (it forces the scroll). */
function Harness({ count, fromUser, shown = true }: { count: number; fromUser: boolean; shown?: boolean }) {
  const { ref, followIfPinned } = useFollowBottomIn<HTMLOListElement>({ itemCount: count, forceToEnd: fromUser });
  return (
    <div>
      <button type="button" onClick={followIfPinned}>
        open
      </button>
      {shown && (
        <ol ref={ref} data-testid="box">
          {Array.from({ length: count }, (_, index) => (
            <li key={index}>entry {index}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  observed: Element[] = [];
  disconnect = vi.fn();
  constructor(private readonly callback: () => void) {
    FakeResizeObserver.instances.push(this);
  }
  observe(target: Element) {
    this.observed.push(target);
  }
  fire() {
    this.callback();
  }
}

let now = 1000;
let content = BOX;
let scrollTop = 0;
let scrollToSpy: ReturnType<typeof vi.fn>;
let pageScroll: ReturnType<typeof vi.fn>;
let intoView: ReturnType<typeof vi.fn>;

function box(): HTMLElement {
  return screen.getByTestId("box");
}

/** Gives the box a size and a scroll position, and a `scrollTo` that moves it like a browser. */
function prepare(element: HTMLElement) {
  Object.defineProperty(element, "scrollHeight", { configurable: true, get: () => content });
  Object.defineProperty(element, "clientHeight", { configurable: true, get: () => BOX });
  Object.defineProperty(element, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = value;
    },
  });
  scrollToSpy = vi.fn((options: ScrollToOptions) => {
    scrollTop = Math.max(0, Number(options.top) - BOX);
  });
  (element as unknown as { scrollTo: unknown }).scrollTo = scrollToSpy;
}

function growBy(by: number) {
  content += by;
}

/** The reader drags the scrollbar: the box moves and reports a scroll event after the hook's own settle time. */
function readerScrollsTo(top: number) {
  now += 5000;
  scrollTop = top;
  act(() => {
    fireEvent.scroll(box());
  });
}

function reducedMotion(on: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({ matches: on && query.includes("reduce"), addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

function setup(count = 1, fromUser = false) {
  const view = render(<Harness count={count} fromUser={fromUser} />);
  prepare(box());
  return view;
}

function add(view: ReturnType<typeof setup>, count: number, fromUser: boolean, by = 60) {
  growBy(by);
  view.rerender(<Harness count={count} fromUser={fromUser} />);
}

beforeEach(() => {
  now = 1000;
  content = BOX;
  scrollTop = 0;
  FakeResizeObserver.instances = [];
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.spyOn(performance, "now").mockImplementation(() => now);
  reducedMotion(false);
  pageScroll = vi.fn();
  intoView = vi.fn();
  vi.stubGlobal("scrollTo", pageScroll);
  Element.prototype.scrollIntoView = intoView as unknown as typeof Element.prototype.scrollIntoView;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("following an assistant entry", () => {
  test("a new entry scrolls the box to its end while the reader is at the bottom", () => {
    const view = setup(1);

    add(view, 2, false);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "auto" });
  });

  test("many entries in a row keep following", () => {
    const view = setup(1);

    for (let count = 2; count <= 8; count += 1) {
      add(view, count, count % 2 === 0);
    }

    expect(scrollTop).toBe(content - BOX);
  });

  test("an entry that grows (a long reply, or text arriving) is followed too", () => {
    const view = setup(1);
    add(view, 2, false);
    scrollToSpy.mockClear();

    growBy(120);
    act(() => FakeResizeObserver.instances.at(-1)?.fire());

    expect(scrollToSpy).toHaveBeenCalledWith({ top: content, behavior: "auto" });
  });

  test("it watches the box and every entry in it for growth", () => {
    setup(3);

    const observer = FakeResizeObserver.instances.at(-1);
    expect(observer?.observed).toContain(box());
    expect(observer?.observed).toHaveLength(1 + 3);
  });
});

describe("the reader's own entry", () => {
  test("scrolls smoothly to the end", () => {
    const view = setup(1);

    add(view, 2, true);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "smooth" });
  });

  test("scrolls even if the reader had scrolled up to read", () => {
    const view = setup(1);
    for (let count = 2; count <= 6; count += 1) {
      add(view, count, false, 100);
    }
    readerScrollsTo(0);
    scrollToSpy.mockClear();

    add(view, 7, true);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "smooth" });
  });

  test("and the reply that follows is followed again, because sending counts as coming back to the bottom", () => {
    const view = setup(1);
    for (let count = 2; count <= 6; count += 1) {
      add(view, count, false, 100);
    }
    readerScrollsTo(0);
    add(view, 7, true);
    scrollToSpy.mockClear();

    add(view, 8, false);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "auto" });
  });

  test("is instant, not animated, when the reader prefers reduced motion", () => {
    reducedMotion(true);
    const view = setup(1);

    add(view, 2, true);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "auto" });
  });
});

describe("a reader who scrolled up", () => {
  function scrolledUp() {
    const view = setup(1);
    for (let count = 2; count <= 6; count += 1) {
      add(view, count, false, 100);
    }
    readerScrollsTo(0);
    scrollToSpy.mockClear();
    return view;
  }

  test("is not pulled back down by a new assistant entry", () => {
    const view = scrolledUp();

    add(view, 7, false);

    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  test("is not pulled back down when an entry grows", () => {
    scrolledUp();

    growBy(200);
    act(() => FakeResizeObserver.instances.at(-1)?.fire());

    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  test("is followed again once they come back near the bottom", () => {
    const view = scrolledUp();

    readerScrollsTo(content - BOX - 10);
    add(view, 7, false);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "auto" });
  });

  test("is still left alone while they are further than a few pixels from the end", () => {
    const view = scrolledUp();

    readerScrollsTo(content - BOX - 200);
    add(view, 7, false);

    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  test("the box's own scrolling is not mistaken for the reader scrolling up", () => {
    const view = setup(1);
    add(view, 2, true); // starts a smooth scroll

    // The browser reports scroll events on the way, while the box is still far from the end.
    scrollTop = 0;
    act(() => {
      fireEvent.scroll(box());
    });
    scrollToSpy.mockClear();
    growBy(80);
    act(() => FakeResizeObserver.instances.at(-1)?.fire());

    expect(scrollToSpy).toHaveBeenCalled();
  });
});

describe("only the box scrolls, never the page", () => {
  test("neither the window nor scrollIntoView is used", () => {
    const view = setup(1);

    add(view, 2, false);
    add(view, 3, true);
    growBy(100);
    act(() => FakeResizeObserver.instances.at(-1)?.fire());

    expect(pageScroll).not.toHaveBeenCalled();
    expect(intoView).not.toHaveBeenCalled();
  });
});

describe("when the box first appears and when it is opened", () => {
  test("a box that is not shown until the first entry still follows from then on", () => {
    const view = render(<Harness count={0} fromUser={false} shown={false} />);
    view.rerender(<Harness count={1} fromUser={false} shown />);
    prepare(box());

    add(view as unknown as ReturnType<typeof setup>, 2, false);

    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: content, behavior: "auto" });
  });

  test("opening it follows only if the reader had been at the bottom", () => {
    const view = setup(1);
    add(view, 2, false);
    scrollToSpy.mockClear();

    fireEvent.click(screen.getByRole("button", { name: "open" }));
    expect(scrollToSpy).toHaveBeenCalledTimes(1);

    for (let count = 3; count <= 6; count += 1) {
      add(view, count, false, 100);
    }
    readerScrollsTo(0);
    scrollToSpy.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "open" }));

    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  test("nothing happens with no entries", () => {
    render(<Harness count={0} fromUser={false} />);
    prepare(box());

    expect(scrollToSpy).not.toHaveBeenCalled();
  });
});

describe("when the browser has no element scrollTo", () => {
  test("it falls back to setting the scroll position", () => {
    const view = setup(1);
    (box() as unknown as { scrollTo: unknown }).scrollTo = undefined;

    add(view, 2, false);

    expect(scrollTop).toBe(content);
  });
});
