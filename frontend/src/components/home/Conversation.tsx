import { useEffect, useRef, useState } from "react";

import type { ItineraryRequest, TripRequest } from "../../contracts/types";
import type { VoiceAdapter } from "../../voice/VoiceAdapter";
import type { VoiceSession } from "../../voice/useVoiceSession";
import { PlanSection } from "../PlanSection";
import { VoiceMode } from "../voice/VoiceMode";
import { PlanTripView } from "../../views/PlanTripView";
import type { ChatMessage } from "./useTripChat";

interface ConversationProps {
  messages: readonly ChatMessage[];
  notice: string;
  busy: boolean;
  error: string | null;
  tripRequest: TripRequest | null;
  itineraryRequest: ItineraryRequest | null;
  adapter: VoiceAdapter | null;
  session: VoiceSession;
}

/**
 * The conversation screen: messages, the shared voice panel while a voice session exists, and the
 * richer views (plan, comparison) which appear here only when the traveller asks for them.
 */
export function Conversation({
  messages,
  notice,
  busy,
  error,
  tripRequest,
  itineraryRequest,
  adapter,
  session,
}: ConversationProps) {
  const [plan, setPlan] = useState<ItineraryRequest | null>(null);
  const [compare, setCompare] = useState<TripRequest | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const voiceShown = session.state.status !== "idle" || session.state.transcript.length > 0;

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, busy, plan, compare]);

  return (
    <div className="conversation">
      <p className="conversation-notice" role="note">
        {notice} Nothing is booked.
      </p>

      {voiceShown && (
        <VoiceMode adapter={adapter} session={session} hideTextInput />
      )}

      <ol className="messages" aria-label="Conversation" aria-live="polite">
        {messages.map((message) => (
          <li key={message.id} className={`message message-${message.from}`}>
            <span className="visually-hidden">{message.from === "you" ? "You: " : "TravelMate: "}</span>
            <span className="message-text">{message.text}</span>
          </li>
        ))}
      </ol>

      {busy && (
        <p className="conversation-status" role="status">
          TravelMate is thinking…
        </p>
      )}
      {error !== null && (
        <p role="alert" className="chat-error">
          {error}
        </p>
      )}

      {(itineraryRequest !== null || tripRequest !== null) && (
        <div className="conversation-actions">
          {itineraryRequest !== null && (
            <button type="button" className="button button-secondary" onClick={() => setPlan(itineraryRequest)}>
              Show the plan
            </button>
          )}
          {tripRequest !== null && (
            <button type="button" className="button button-secondary" onClick={() => setCompare(tripRequest)}>
              Use these details
            </button>
          )}
        </div>
      )}

      {plan !== null && <PlanSection key={JSON.stringify(plan)} request={plan} />}
      {compare !== null && (
        <div className="conversation-compare">
          <PlanTripView key={JSON.stringify(compare)} embedded initialRequest={compare} />
        </div>
      )}
      <div ref={end} />
    </div>
  );
}
