import { useState } from "react";

import type { sendChatTurn } from "../api/chat";
import { Composer } from "../components/home/Composer";
import { Conversation } from "../components/home/Conversation";
import { MicIcon } from "../components/home/icons";
import { useTripChat } from "../components/home/useTripChat";
import { VoiceButton } from "../components/home/VoiceButton";
import { chooseVoiceAdapter } from "../voice/config";
import type { VoiceAdapter } from "../voice/VoiceAdapter";
import { useVoiceSession } from "../voice/useVoiceSession";

interface HomeViewProps {
  /** Replaceable in tests. Left out, the build's own choice applies (`null` in production). */
  adapter?: VoiceAdapter | null;
  /**
   * Whether typed chat can work. The backend serves it only in development, so a production build
   * shows the box switched off with a plain reason. Defaults to the build mode.
   */
  chatAvailable?: boolean;
  /** Replaceable in tests. */
  send?: typeof sendChatTurn;
}

type TripChat = ReturnType<typeof useTripChat>;

/** What production gets: no chat code at all. The box is switched off and nothing is sent. */
function useUnavailableChat(): TripChat {
  return {
    messages: [],
    notice: "",
    busy: false,
    error: null,
    tripRequest: null,
    itineraryRequest: null,
    submit: () => Promise.resolve(),
  };
}

// Build-time constants: a production build drops the chat and the conversation screen entirely
// (the backend refuses to serve chat in production; ADR 0004).
const useChat = import.meta.env.DEV ? useTripChat : useUnavailableChat;
const ConversationScreen = import.meta.env.DEV ? Conversation : null;

const EXAMPLE = "For example: I want to go to Goa this weekend. Plan my trip.";

/**
 * The home screen: a voice button and a message box, nothing else. The conversation view appears
 * only once the traveller starts talking or typing. Voice uses the existing session machinery;
 * typed messages use the existing chat endpoint.
 */
export function HomeView({
  adapter: adapterOverride,
  chatAvailable = import.meta.env.DEV,
  send,
}: HomeViewProps) {
  // `chooseVoiceAdapter()` is `null` in a production build: no real voice back end exists yet.
  const [adapter] = useState<VoiceAdapter | null>(() =>
    adapterOverride !== undefined ? adapterOverride : chooseVoiceAdapter(),
  );
  const session = useVoiceSession(adapter);
  const chat = useChat(send);
  const [text, setText] = useState("");
  const [engaged, setEngaged] = useState(false);

  function submit() {
    if (!chatAvailable || text.trim() === "") {
      return;
    }
    const message = text;
    setText("");
    setEngaged(true);
    void chat.submit(message);
  }

  function startVoice() {
    setEngaged(true);
    void session.startVoice();
  }

  const connecting = session.state.status === "connecting";
  const inVoiceSession = session.state.status !== "idle" && session.state.status !== "error";

  return (
    <div className={`home${engaged ? " home-chat" : ""}`}>
      {engaged && ConversationScreen !== null ? (
        <ConversationScreen
          messages={chat.messages}
          notice={chat.notice}
          busy={chat.busy}
          error={chat.error}
          tripRequest={chat.tripRequest}
          itineraryRequest={chat.itineraryRequest}
          adapter={adapter}
          session={session}
        />
      ) : (
        <section className="home-hero" aria-labelledby="home-title">
          <h1 id="home-title">Where do you want to go?</h1>
          <p className="home-subtitle">Your personal AI travel planner.</p>
          <VoiceButton adapter={adapter} connecting={connecting} onStart={startVoice} />
        </section>
      )}

      <Composer
        value={text}
        onChange={setText}
        onSubmit={submit}
        disabled={!chatAvailable}
        busy={chat.busy}
        example={engaged ? undefined : EXAMPLE}
        footnote={
          chatAvailable && import.meta.env.DEV
            ? engaged
              ? undefined
              : "Development stand-in, not a language model. Nothing is booked."
            : "Chat isn't available yet in this version."
        }
        actions={
          engaged ? (
            <button
              type="button"
              className="mic-button"
              onClick={startVoice}
              disabled={adapter === null || connecting || inVoiceSession}
              aria-label="Start a voice conversation"
            >
              <MicIcon />
            </button>
          ) : undefined
        }
      />
    </div>
  );
}
