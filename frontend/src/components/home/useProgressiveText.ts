import { useCallback, useEffect, useMemo, useState } from "react";

/**
 * Presentation-only progressive reveal of text the browser already has in full.
 *
 * This is NOT streaming from the model or the server: the server sends each reply whole, and this
 * only shows it a piece at a time. Callers must say so on screen. If a real stream ever exists, the
 * same hook works with text that keeps growing (it continues where it was) and with no other change.
 */

const TICK_MS = 30;
/** Roughly 55 characters a second, so short replies take about a second. */
const MS_PER_CHAR = 18;
const MIN_MS = 350;
/** However long the text is, it is fully shown within this. */
const MAX_MS = 2000;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface ProgressiveText {
  /** The part of the text to show now. */
  shown: string;
  /** Everything is shown. */
  done: boolean;
  /** Show everything at once. */
  skip: () => void;
}

/**
 * @param text The whole text, or the text so far if it is still growing.
 * @param enabled Reveal it progressively. When false, or when the reader prefers reduced motion,
 *   all of it is shown at once.
 */
export function useProgressiveText(text: string, enabled: boolean): ProgressiveText {
  const characters = useMemo(() => Array.from(text), [text]);
  const total = characters.length;
  const animate = enabled && !prefersReducedMotion();
  const [count, setCount] = useState(0);
  const [previous, setPrevious] = useState(text);

  // Text that is not a continuation of what was shown starts again from the beginning.
  if (previous !== text) {
    setPrevious(text);
    if (!text.startsWith(previous)) {
      setCount(0);
    }
  }

  const shownCount = animate ? Math.min(count, total) : total;
  const done = shownCount >= total;

  useEffect(() => {
    if (!animate || done) {
      return;
    }
    const duration = Math.min(MAX_MS, Math.max(MIN_MS, total * MS_PER_CHAR));
    const step = Math.max(1, Math.ceil(total / (duration / TICK_MS)));
    const timer = window.setInterval(() => {
      setCount((current) => Math.min(total, current + step));
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [animate, done, total]);

  const skip = useCallback(() => setCount(Number.POSITIVE_INFINITY), []);

  const shown = useMemo(
    () => (shownCount >= total ? text : characters.slice(0, shownCount).join("")),
    [characters, shownCount, text, total],
  );

  return { shown, done, skip };
}
