import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { ChatApiError, sendChatTurn, type ChatDraft, type ChatTurn } from "../api/chat";
import type { ItineraryRequest, TripRequest } from "../contracts/types";

interface TripChatProps {
  /** Called when the traveller accepts the details the chat collected. */
  onUseRequest: (request: TripRequest) => void;
  /** Called when the traveller asks to see the plan for the itinerary request. */
  onUseItinerary?: (request: ItineraryRequest) => void;
  /** Replaceable in tests. */
  send?: typeof sendChatTurn;
}

interface Line {
  from: "you" | "assistant";
  text: string;
}

const INTRO_NOTICE =
  "Development stand-in: it reads a few simple patterns in English. It is not a language model, and no model is connected.";

function failureText(error: unknown): string {
  if (error instanceof ChatApiError) {
    if (error.status === 404) {
      return "Chat is not switched on. Start the backend with CONVERSATION_ENABLED=true and its limits (see .env.example).";
    }
    if (error.status === null) {
      return "The server could not be reached. Is the backend running?";
    }
    return error.detail ?? `The server answered HTTP ${error.status}.`;
  }
  return "Something went wrong. Please try again.";
}

/** Typed chat that collects a trip request. It cannot search, book or pay. */
export function TripChat({ onUseRequest, onUseItinerary, send = sendChatTurn }: TripChatProps) {
  const [lines, setLines] = useState<Line[]>([]);
  const [draft, setDraft] = useState<ChatDraft | null>(null);
  const [ready, setReady] = useState<TripRequest | null>(null);
  const [readyPlan, setReadyPlan] = useState<ItineraryRequest | null>(null);
  const [notice, setNotice] = useState(INTRO_NOTICE);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const pending = useRef<AbortController | null>(null);

  useEffect(() => () => pending.current?.abort(), []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (message === "" || busy) {
      return;
    }
    setText("");
    setError(null);
    setBusy(true);
    setLines((before) => [...before, { from: "you", text: message }]);
    const controller = new AbortController();
    pending.current = controller;
    try {
      const turn: ChatTurn = await send(message, draft, controller.signal);
      setDraft(turn.draft);
      setReady(turn.status === "READY_FOR_REVIEW" ? turn.tripRequest : null);
      setReadyPlan(turn.status === "READY_FOR_REVIEW" ? turn.itineraryRequest : null);
      setNotice(turn.modelNotice);
      setLines((before) => [...before, { from: "assistant", text: turn.reply }]);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(failureText(caught));
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  function startOver() {
    pending.current?.abort();
    pending.current = null;
    setLines([]);
    setDraft(null);
    setReady(null);
    setReadyPlan(null);
    setError(null);
    setText("");
    setBusy(false);
  }

  return (
    <section className="trip-chat" aria-labelledby="trip-chat-title">
      <h2 id="trip-chat-title">Describe your trip in a message</h2>
      <p className="field-hint">{notice}</p>
      <ol className="chat-lines" aria-label="Conversation" aria-live="polite">
        {lines.map((line, index) => (
          <li key={index} className={`chat-line chat-line-${line.from}`}>
            <span className="chat-speaker">{line.from === "you" ? "You" : "TravelMate"}: </span>
            {line.text}
          </li>
        ))}
      </ol>
      {error !== null && (
        <p role="alert" className="chat-error">
          {error}
        </p>
      )}
      <form className="voice-text-fallback" onSubmit={handleSubmit}>
        <label htmlFor={inputId}>For example: from Indore to Goa on 12 December, 2 people</label>
        <div className="voice-text-row">
          <input
            id={inputId}
            type="text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={busy}
            autoComplete="off"
          />
          <button type="submit" className="button button-primary" disabled={busy || text.trim() === ""}>
            Send
          </button>
          <button type="button" className="button" onClick={startOver}>
            Start over
          </button>
        </div>
      </form>
      {readyPlan !== null && onUseItinerary !== undefined && (
        <div className="chat-ready">
          <p>
            These details are ready. The plan is written by the server and labelled with where it
            came from: a scripted sample until a language model is switched on. Nothing is
            booked.
          </p>
          <button
            type="button"
            className="button button-primary"
            onClick={() => onUseItinerary(readyPlan)}
          >
            Show the plan
          </button>
        </div>
      )}
      {ready !== null && (
        <div className="chat-ready">
          <p>
            These details are ready. Using them previews demo data only; nothing is booked.
          </p>
          <button type="button" className="button button-primary" onClick={() => onUseRequest(ready)}>
            Use these details
          </button>
        </div>
      )}
    </section>
  );
}
