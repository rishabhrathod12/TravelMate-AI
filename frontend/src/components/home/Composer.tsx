import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { ArrowUpIcon } from "./icons";

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** The whole box is off (for example chat is not available in this build). */
  disabled?: boolean;
  /** A reply is on its way: typing stays possible, sending waits. */
  busy?: boolean;
  /** Muted example text shown inside the box above the input. */
  example?: string;
  /** Muted line under the box. */
  footnote?: string;
  /** Extra control placed at the left of the send button, such as a small voice button. */
  actions?: ReactNode;
}

const MAX_HEIGHT_PX = 200;

/** A large rounded message box. Enter sends, Shift+Enter adds a line. */
export function Composer({
  value,
  onChange,
  onSubmit,
  disabled = false,
  busy = false,
  example,
  footnote,
  actions,
}: ComposerProps) {
  const inputId = useId();
  const exampleId = useId();
  const footnoteId = useId();
  const area = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && !busy && value.trim() !== "";
  const showExample = example !== undefined && !disabled;
  const described = [showExample ? exampleId : null, footnote !== undefined ? footnoteId : null]
    .filter((id): id is string => id !== null)
    .join(" ");

  // Grow with the text, up to a limit, then scroll.
  useEffect(() => {
    const element = area.current;
    if (element !== null) {
      element.style.height = "auto";
      element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
    }
  }, [value]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // `isComposing`: Enter that confirms a text-input-method choice must not send the message.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) {
        onSubmit();
      }
    }
  }

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) {
          onSubmit();
        }
      }}
    >
      <div className={`composer-box${disabled ? " composer-box-disabled" : ""}`}>
        {showExample && (
          <p id={exampleId} className="composer-example">
            {example}
          </p>
        )}
        <label htmlFor={inputId} className="visually-hidden">
          Message TravelMate
        </label>
        <textarea
          id={inputId}
          ref={area}
          className="composer-input"
          rows={1}
          value={value}
          placeholder="Ask anything about your trip..."
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          aria-describedby={described === "" ? undefined : described}
        />
        <div className="composer-actions">
          {actions}
          <button type="submit" className="send-button" disabled={!canSend} aria-label="Send message">
            <ArrowUpIcon />
          </button>
        </div>
      </div>
      {footnote !== undefined && (
        <p id={footnoteId} className="composer-footnote">
          {footnote}
        </p>
      )}
    </form>
  );
}
