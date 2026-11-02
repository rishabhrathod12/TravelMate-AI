import { useCallback, useEffect, useRef, useState } from "react";

import { ChatApiError, sendChatTurn, type ChatDraft, type ChatTurn } from "../../api/chat";
import type { ItineraryRequest, TripRequest } from "../../contracts/types";

export interface ChatMessage {
  id: number;
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

  return { messages, notice, busy, error, tripRequest, itineraryRequest, submit };
}
