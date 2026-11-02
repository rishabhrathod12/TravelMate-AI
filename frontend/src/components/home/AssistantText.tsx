import { useEffect, useRef } from "react";

import { renderMarkdown } from "../../lib/markdown";
import { useProgressiveText } from "./useProgressiveText";

interface AssistantTextProps {
  /** The whole reply, as the server sent it. */
  text: string;
  /**
   * Show it progressively. Only the newest reply is revealed; anything older, or any reply once the
   * reader has sent another message, is shown whole.
   */
  reveal: boolean;
  /** Where focus goes if the skip button had it when it disappears. */
  focusAfterSkip?: () => HTMLElement | null;
}

/**
 * One assistant reply, with Markdown. While it is being revealed the animated text is hidden from
 * assistive technology (so it is not read out letter by letter), and the finished reply replaces it
 * in the same place and at the same size, so it is announced once and nothing jumps.
 *
 * This is a presentation effect of the browser. The server sends the reply whole; the conversation
 * says so on screen.
 */
export function AssistantText({ text, reveal, focusAfterSkip }: AssistantTextProps) {
  const { shown, done, skip } = useProgressiveText(text, reveal);
  const skipButton = useRef<HTMLButtonElement>(null);

  // Escape shows everything at once.
  useEffect(() => {
    if (done) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        skip();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [done, skip]);

  function skipAll() {
    const hadFocus = document.activeElement === skipButton.current;
    skip();
    if (hadFocus) {
      // The button is about to disappear; do not leave the keyboard user at the top of the page.
      window.setTimeout(() => focusAfterSkip?.()?.focus(), 0);
    }
  }

  if (done) {
    return <div className="markdown">{renderMarkdown(text)}</div>;
  }
  return (
    <>
      <div className="reveal-stack" aria-hidden="true">
        {/* Invisible, but it gives the bubble its final size from the first frame. */}
        <div className="reveal-full markdown">{renderMarkdown(text, { inert: true })}</div>
        <div className="reveal-visible markdown">{renderMarkdown(shown, { partial: true, inert: true })}</div>
      </div>
      <button
        ref={skipButton}
        type="button"
        className="reveal-skip"
        onClick={skipAll}
        aria-label="Show the whole reply"
        title="Show the whole reply (Esc)"
      >
        <span aria-hidden="true">»</span>
      </button>
    </>
  );
}
