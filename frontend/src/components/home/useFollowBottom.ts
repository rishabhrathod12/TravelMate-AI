import { useCallback, useEffect, useRef, type RefObject } from "react";

/** How far below the visible area the end of the conversation may be and still count as "at the bottom". */
const NEAR_BOTTOM_PX = 80;
/** A smooth scroll reports scroll events on the way; they say nothing about where the reader is. */
const SMOOTH_SCROLL_MS = 800;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface FollowBottomOptions {
  /** Changes when a message is added. */
  messageCount: number;
  /** Whether the newest message is the reader's own. */
  lastFromUser: boolean;
}

interface FollowBottom {
  /** Put on the element that holds the whole conversation, so any growth in it is noticed. */
  contentRef: RefObject<HTMLDivElement | null>;
  /** Put on an empty element after the last item. Its `scroll-margin-bottom` leaves room for the composer. */
  endRef: RefObject<HTMLDivElement | null>;
}

/**
 * Keeps the newest part of a conversation in view, the way a chat app does, on a page that scrolls
 * as a whole:
 *
 * - Sending a message always scrolls to it, even if the reader had scrolled up.
 * - Anything else that makes the conversation taller (a reply, an error, a voice panel, a plan that
 *   finishes loading, text arriving bit by bit) is followed only while the reader is near the bottom.
 * - A reader who scrolls up to read is left alone, and following resumes when they come back down.
 * - Scrolling stops short of the end by the end element's `scroll-margin-bottom`, so the sticky
 *   composer never covers the newest message.
 * - Only message-sized growth is followed. If the conversation grows by more than one screen in a
 *   single step, a whole panel (the plan, the comparison view) has arrived, and the reader is left
 *   where its start is in view rather than flung to its far end.
 * - Growth is followed with an instant scroll, so continuous growth never stacks animations. Only a
 *   sent message scrolls smoothly, and not at all when the reader prefers reduced motion. If content
 *   grows while that smooth scroll is still running, the scroll is retargeted at the new end, so a
 *   reply is never left partly out of view.
 */
export function useFollowBottom({ messageCount, lastFromUser }: FollowBottomOptions): FollowBottom {
  const contentRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const smoothUntil = useRef(0);
  const height = useRef(0);
  const grewBy = useRef(0);

  const scrollToEnd = useCallback((behavior: ScrollBehavior) => {
    const end = endRef.current;
    if (end === null) {
      return;
    }
    if (behavior === "smooth") {
      smoothUntil.current = performance.now() + SMOOTH_SCROLL_MS;
    }
    end.scrollIntoView?.({ block: "end", behavior });
  }, []);

  // Where the reader is: is the end of the conversation within reach of the visible area?
  useEffect(() => {
    function isNearBottom(): boolean {
      const end = endRef.current;
      if (end === null) {
        return true;
      }
      const reserved = Number.parseFloat(getComputedStyle(end).scrollMarginBottom) || 0;
      const visibleBottom = window.innerHeight - reserved;
      return end.getBoundingClientRect().bottom - visibleBottom <= NEAR_BOTTOM_PX;
    }
    function onScroll() {
      if (performance.now() < smoothUntil.current) {
        return;
      }
      pinned.current = isNearBottom();
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Growth of the conversation: follow it only while the reader is at the bottom.
  useEffect(() => {
    const content = contentRef.current;
    if (content === null || typeof ResizeObserver === "undefined") {
      return;
    }
    let frame = 0;
    height.current = content.getBoundingClientRect().height;
    function follow() {
      frame = 0;
      const grew = grewBy.current;
      grewBy.current = 0;
      if (!pinned.current || grew > window.innerHeight) {
        return;
      }
      // While a smooth scroll is still running, asking for a smooth scroll again retargets it at the
      // new end. An instant jump would cut it short, and waiting would leave the new content hidden.
      scrollToEnd(performance.now() < smoothUntil.current ? "smooth" : "auto");
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1];
      const now = entry?.borderBoxSize?.[0]?.blockSize ?? entry?.contentRect.height ?? height.current;
      const change = now - height.current;
      height.current = now;
      if (change <= 0) {
        return; // a conversation that got shorter is never a reason to scroll
      }
      grewBy.current += change;
      if (frame === 0) {
        frame = requestAnimationFrame(follow);
      }
    });
    observer.observe(content);
    return () => {
      observer.disconnect();
      if (frame !== 0) {
        cancelAnimationFrame(frame);
      }
    };
  }, [scrollToEnd]);

  // A new message. The reader's own always scrolls; a reply is handled by the size observer, with
  // this as the fallback where there is none.
  useEffect(() => {
    if (messageCount === 0) {
      return;
    }
    if (lastFromUser) {
      pinned.current = true;
      scrollToEnd(prefersReducedMotion() ? "auto" : "smooth");
    } else if (typeof ResizeObserver === "undefined" && pinned.current) {
      scrollToEnd("auto");
    }
  }, [messageCount, lastFromUser, scrollToEnd]);

  return { contentRef, endRef };
}
