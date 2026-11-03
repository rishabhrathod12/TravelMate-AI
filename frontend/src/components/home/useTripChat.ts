import { useCallback, useEffect, useRef, useState } from "react";

import { ChatApiError, sendChatTurn, type ChatDraft, type ChatTurn } from "../../api/chat";
import type { ItineraryRequest, TripRequest } from "../../contracts/types";

export interface ChatMessage {
  id: number;
  from: "you" | "assistant";
  text: string;
  /**
   * Written by this page, not sent by the server (for example the planning questions). It is
   * shown whole: the "shown progressively" note is only about replies the server sent.
   */
  local?: boolean;
}

// Neutral on purpose: which reader answers (the offline stand-in or an OpenAI model) is decided by
// the server and shown from its first reply on, so this must not claim either.
const INTRO_NOTICE = "TravelMate reads the details you state and asks for any that are missing.";

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

/**
 * The typed conversation, kept for this session only. It uses the existing chat endpoint: the
 * server keeps nothing between turns, so the draft it returns is sent back with the next message.
 * It cannot search, book or pay.
 */
export function useTripChat(send: typeof sendChatTurn = sendChatTurn) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<ChatDraft | null>(null);
  const [tripRequest, setTripRequest] = useState<TripRequest | null>(null);
  const [itineraryRequest, setItineraryRequest] = useState<ItineraryRequest | null>(null);
  const [notice, setNotice] = useState(INTRO_NOTICE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stopped, setStopped] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  useEffect(() => () => pending.current?.abort(), []);

  const submit = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (message === "" || pending.current !== null) {
        return;
      }
      setError(null);
      setStopped(false);
      setBusy(true);
      setMessages((before) => [...before, { id: nextId.current++, from: "you", text: message }]);
      const controller = new AbortController();
      pending.current = controller;
      try {
        const turn: ChatTurn = await send(message, draft, controller.signal);
        setDraft(turn.draft);
        const ready = turn.status === "READY_FOR_REVIEW";
        setTripRequest(ready ? turn.tripRequest : null);
        setItineraryRequest(ready ? turn.itineraryRequest : null);
        setNotice(turn.modelNotice);
        setMessages((before) => [
          ...before,
          { id: nextId.current++, from: "assistant", text: turn.reply },
        ]);
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
    },
    [draft, send],
  );

  /** Adds a line to the conversation without asking the server: the page's own question or the reader's answer to it. */
  const addMessage = useCallback((from: "you" | "assistant", text: string) => {
    setMessages((before) => [...before, { id: nextId.current++, from, text, local: true }]);
  }, []);

  /**
   * Stops waiting for the reply to the message just sent. The request is cancelled in the browser;
   * the message stays in the conversation, unanswered, and the reader may send it again.
   */
  const cancel = useCallback(() => {
    const controller = pending.current;
    if (controller === null) {
      return;
    }
    controller.abort();
    pending.current = null;
    setBusy(false);
    setStopped(true);
  }, []);

  return {
    messages,
    notice,
    busy,
    error,
    stopped,
    tripRequest,
    itineraryRequest,
    submit,
    cancel,
    addMessage,
  };
}
