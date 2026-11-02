import { useState } from "react";

import type { ItineraryRequest, TripRequest } from "../../contracts/types";
import type { VoiceAdapter } from "../../voice/VoiceAdapter";
import type { VoiceSession } from "../../voice/useVoiceSession";
import { PlanSection } from "../PlanSection";
import { VoiceMode } from "../voice/VoiceMode";
import { PlanTripView } from "../../views/PlanTripView";
import { AssistantText } from "./AssistantText";
import { RunPanel } from "./RunPanel";
import { useFollowBottom } from "./useFollowBottom";
import type { PlanningRunController } from "./usePlanningRun";
import type { ChatMessage } from "./useTripChat";

/** The message box, so a keyboard user who skipped a reveal lands somewhere useful. */
function focusComposer(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".composer-input");
}

interface ConversationProps {
  messages: readonly ChatMessage[];
  notice: string;
  busy: boolean;
  error: string | null;
  /** The reader stopped waiting for the last reply. */
  stopped: boolean;
  /** Stop waiting for the reply that is on its way. */
  onStop: () => void;
  tripRequest: TripRequest | null;
  itineraryRequest: ItineraryRequest | null;
  adapter: VoiceAdapter | null;
  session: VoiceSession;
  /** The planning journey: asking for rooms, running the workflow, showing its choices and results. */
  planning: PlanningRunController;
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
  stopped,
  onStop,
  tripRequest,
  itineraryRequest,
  adapter,
  session,
  planning,
}: ConversationProps) {
  const [plan, setPlan] = useState<ItineraryRequest | null>(null);
  const [compare, setCompare] = useState<TripRequest | null>(null);
  const voiceShown = session.state.status !== "idle" || session.state.transcript.length > 0;

  // Follows the newest content while the reader is at the bottom; leaves a reader who scrolled up
  // alone (see the hook).
  const lastMessage = messages[messages.length - 1];
  const { contentRef, endRef } = useFollowBottom({
    messageCount: messages.length,
    lastFromUser: lastMessage?.from === "you",
  });

  return (
    <div className="conversation" ref={contentRef}>
      {/* The page's one level-one heading while the conversation replaces the home heading. */}
      <h1 className="visually-hidden">Conversation with TravelMate</h1>
      <p className="conversation-notice" role="note">
        {notice} Nothing is booked. Replies are shown progressively by your browser; the server sends
        each one whole. Esc shows a reply at once.
      </p>

      {voiceShown && (
        <VoiceMode adapter={adapter} session={session} hideTextInput />
      )}

      <ol className="messages" aria-label="Conversation" aria-live="polite">
        {messages.map((message, index) => (
          <li key={message.id} className={`message message-${message.from}`}>
            <span className="visually-hidden">{message.from === "you" ? "You: " : "TravelMate: "}</span>
            {message.from === "you" ? (
              <span className="message-text">{message.text}</span>
            ) : (
              <div className="message-text">
                {/* Only the newest reply is revealed; once the reader writes again it is whole. */}
                <AssistantText
                  text={message.text}
                  reveal={index === messages.length - 1 && message.local !== true}
                  focusAfterSkip={focusComposer}
                />
              </div>
            )}
          </li>
        ))}
      </ol>

      {busy && (
        <div className="conversation-status">
          <p role="status">
            <span className="thinking-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            TravelMate is thinking…
          </p>
          <button type="button" className="button button-small button-quiet" onClick={onStop}>
            Stop
          </button>
        </div>
      )}
      {stopped && !busy && (
        <p className="conversation-status" role="status">
          You stopped this reply. Your message was not answered; send it again if you like.
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
            <button
              type="button"
              className="button button-secondary"
              disabled={!planning.canStart}
              onClick={planning.begin}
            >
              Plan this trip
            </button>
          )}
          {tripRequest !== null && (
            <button type="button" className="button button-secondary" onClick={() => setCompare(tripRequest)}>
              Use these details
            </button>
          )}
        </div>
      )}

      <RunPanel planning={planning} />

      {plan !== null && <PlanSection key={JSON.stringify(plan)} request={plan} />}
      {compare !== null && (
        <div className="conversation-compare">
          <PlanTripView key={JSON.stringify(compare)} embedded initialRequest={compare} />
        </div>
      )}
      <div ref={endRef} className="conversation-end" aria-hidden="true" />
    </div>
  );
}
