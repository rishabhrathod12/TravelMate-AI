import { useCallback, useEffect, useRef } from "react";

/** How far above the very end the reader may be and still count as "at the bottom". */
const NEAR_BOTTOM_PX = 48;
/** A smooth scroll reports scroll events on the way; they say nothing about where the reader is. */
const SMOOTH_SCROLL_MS = 700;
/** An instant scroll reports its scroll event a moment later, which is also not the reader. */
const INSTANT_SCROLL_MS = 120;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface FollowBottomInOptions {
  /** Changes when an entry is added. */
  itemCount: number;
  /**
   * Whether the newest entry is something the reader deliberately sent (a typed message). That
   * always scrolls to the end. A spoken entry is not: it arrives by itself while the reader may be
   * reading older lines, so it is followed only like any other entry.
   */
  forceToEnd: boolean;
}

interface FollowBottomIn<T extends HTMLElement> {
  /** Put on the element that scrolls (the one with its own overflow), as its `ref`. */
  ref: (element: T | null) => void;
  /** For when the box is opened or resized: follow, but only if the reader was at the bottom. */
  followIfPinned: () => void;
}

/**
 * Keeps the newest entry of a scrollable box in view, the way a chat app does. It scrolls the box
 * itself and never the page (it uses the box's own `scrollTop`, not `scrollIntoView`), so the rest
 * of the screen and the composer stay where they are.
 *
 * - A message the reader just sent (typed) always scrolls to the end, even if they had scrolled up.
 * - Anything else that makes the box's content taller (an assistant entry, what they said aloud,
 *   an entry whose text grows, a long entry) is followed only while the reader is within a few
 *   pixels of the end.
 * - A reader who scrolls up to read is left alone; following resumes when they come back down.
 * - Growth is followed with an instant scroll, so continuous growth never stacks animations. Only
 *   the reader's sent message scrolls smoothly, and not at all when they prefer reduced motion.
 *
 * Its counterpart for a conversation that scrolls the whole page is `useFollowBottom`.
 */
export function useFollowBottomIn<T extends HTMLElement>({
  itemCount,
  forceToEnd,
}: FollowBottomInOptions): FollowBottomIn<T> {
  const element = useRef<T | null>(null);
  const detach = useRef<(() => void) | null>(null);
  const observer = useRef<ResizeObserver | null>(null);
  const pinned = useRef(true);
  const ignoreScrollUntil = useRef(0);

  const scrollToEnd = useCallback((behavior: ScrollBehavior) => {
    const box = element.current;
    if (box === null) {
      return;
    }
    ignoreScrollUntil.current = performance.now() + (behavior === "smooth" ? SMOOTH_SCROLL_MS : INSTANT_SCROLL_MS);
    if (typeof box.scrollTo === "function") {
      box.scrollTo({ top: box.scrollHeight, behavior });
    } else {
      box.scrollTop = box.scrollHeight;
    }
  }, []);

  // A callback ref, because the box can appear after the hook first runs (it is not shown until
  // there is a first entry), and the scroll listener has to be attached whenever it does.
  const ref = useCallback((box: T | null) => {
    detach.current?.();
    detach.current = null;
    element.current = box;
    if (box === null) {
      return;
    }
    function onScroll() {
      if (performance.now() < ignoreScrollUntil.current) {
        return;
      }
      const target = element.current;
      if (target === null) {
        return;
      }
      pinned.current = target.scrollHeight - target.scrollTop - target.clientHeight <= NEAR_BOTTOM_PX;
    }
    box.addEventListener("scroll", onScroll, { passive: true });
    detach.current = () => box.removeEventListener("scroll", onScroll);
  }, []);

  // Growth of any entry (not just a new one) is followed while the reader is at the bottom.
  useEffect(() => {
    const box = element.current;
    if (box === null || typeof ResizeObserver === "undefined") {
      return;
    }
    const watcher = new ResizeObserver(() => {
      if (pinned.current) {
        scrollToEnd("auto");
      }
    });
    observer.current = watcher;
    watcher.observe(box);
    for (const child of Array.from(box.children)) {
      watcher.observe(child);
    }
    return () => {
      watcher.disconnect();
      observer.current = null;
    };
  }, [itemCount, scrollToEnd]);

  // A new entry. A message the reader sent always scrolls; any other is followed only while at the
  // bottom.
  useEffect(() => {
    if (itemCount === 0) {
      return;
    }
    if (forceToEnd) {
      pinned.current = true;
      scrollToEnd(prefersReducedMotion() ? "auto" : "smooth");
    } else if (pinned.current) {
      scrollToEnd("auto");
    }
  }, [itemCount, forceToEnd, scrollToEnd]);

  useEffect(
    () => () => {
      detach.current?.();
      detach.current = null;
    },
    [],
  );

  const followIfPinned = useCallback(() => {
    if (pinned.current) {
      scrollToEnd("auto");
    }
  }, [scrollToEnd]);

  return { ref, followIfPinned };
}
