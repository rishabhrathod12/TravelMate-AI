import { useId, useState, type FormEvent } from "react";

interface TextChatProps {
  disabled: boolean;
  onSend: (text: string) => void;
}

/** The typed alternative to speaking. It works without a microphone. */
export function TextChat({ disabled, onSend }: TextChatProps) {
  const [draft, setDraft] = useState("");
  const inputId = useId();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (draft.trim() === "") {
      return;
    }
    onSend(draft);
    setDraft("");
  }

  return (
    <form className="voice-text-fallback" onSubmit={handleSubmit}>
      <label htmlFor={inputId}>Or type a message</label>
      <div className="voice-text-row">
        <input
          id={inputId}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={disabled}
          autoComplete="off"
        />
        <button
          type="submit"
          className="button button-primary"
          disabled={disabled || draft.trim() === ""}
        >
          Send
        </button>
      </div>
    </form>
  );
}
