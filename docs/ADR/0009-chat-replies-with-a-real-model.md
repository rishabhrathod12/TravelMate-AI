# ADR 0009: Chat replies written with a real model, facts from read-only tools

Status: **Accepted by the project owner on 2026-11-03** (the owner approved the full proposal, phases 1 to 5, and asked to use the OpenAI model with the key they supplied in their own `.env`). Reopens the chat design that PRD A23 had closed. Related: ADR 0004 (chat first), ADR 0008 (live voice), ADR 0001 (the one OpenAI SDK module), SECURITY section 3 and section 12.

## Context

Once the OpenAI reader was connected, the chat still gave repetitive, irrelevant answers. The cause was not only the missing model. In `ConversationManager` the model's one job was to extract trip details as JSON. Every reply was a canned string chosen by code (the `QUESTIONS` table and fixed templates), so "Hi", "How are you?", "What transport is there?", "What is the weather in Goa?" all got the next missing-field question. The chat also never called the research tools, and it knew nothing of earlier turns.

## Decision

1. **One conversation system, not two.** The existing `ConversationManager` stays the only conversation logic. It still extracts details through `LLMClient.structured_complete`, and every detail is still checked against the traveller's own words (`app.conversation.claims`) and the domain models. Nothing the model says becomes a date, a count, a room number or a place unless the traveller wrote it.
2. **Code decides what a reply may say; the model only words it.** The plain reply is always built by code first (a question, a read-back, facts). With live calls on, a second call (`LLMClient.complete`, no tools) may reword it in the traveller's language. The wording is used only if it passes `check_reply`: every number in it already appears in the facts, the traveller's own messages, the draft or the plain reply; it makes no booking, payment or confirmation claim or offer; a date or trip read-back keeps its numbers; it is plain text of limited length. Otherwise the plain reply is shown. A failed, slow or rate-limited call also falls back to the plain reply.
3. **Small talk is answered by code.** A message that is only a greeting, thanks, "how are you" or goodbye (English, Hindi or Hinglish) gets a fixed line plus the next question. It costs no model call.
4. **Intents choose facts and wording, nothing else.** `Intent` (trip details, transport, compare, cost, weather, plan, change, book request, small talk, other) is reported by the model or guessed by code from plain words. A request to book is always found by code, and a model cannot raise it by itself. No intent starts anything. A request to book is answered with a fixed notice that booking is not available.
5. **Facts come from the research tools, labelled.** For transport, comparison, cost and weather questions the API layer (`app/api/chat_facts.py`, not the conversation package) calls the existing read-only tools only when the draft holds every input. It never guesses a traveller count or a date. Each line carries its provenance (MOCK, LIVE, CACHED_LIVE), and a code-written footer states the label even if the model leaves it out. A provider failure or empty answer is stated plainly. No trip total is added up in the chat: a cost answer lists what was found and says the estimate is made when the trip is planned (PRD Q12, Q13, Q18).
6. **History.** The browser sends the last turns, bounded (40 lines of at most 2000 characters at the API, then trimmed by `CONVERSATION_HISTORY_MAX_TURNS` and `CONVERSATION_HISTORY_MAX_CHARS`). The server stores nothing. History is passed to the model only inside the delimited data block.
7. **Planning stays on the existing path.** When the draft is complete the chat still returns a validated `trip_request` or `itinerary_request`. Running the LangGraph planning workflow, choosing options and the approval path stay in the planning API and its screens, as before. The chat model cannot start a run, select an option, approve or execute anything. `BOOKING_ENABLED` stays false and `app/conversation` still must not import or name booking.
8. **Language.** The extraction and reply prompts tell the model to read and answer in English, Hindi (Devanagari or Roman letters) and Hinglish. Dates still need an English month name (`conversation/dates.py`) and a place must appear in the message as written. Provider lookups only know the places the providers know, so a Devanagari place name will reach the tools as written and may find nothing.
9. **Deliberate small defaults.** The settings rule is "no hidden defaults". For the optional reply and history limits only, named constants in `app/conversation/reply_writer.py` apply when `CONVERSATION_REPLY_*` and `CONVERSATION_HISTORY_*` are unset (300 output tokens, 20 seconds, 6 turns, 2000 characters), so the owner's existing `.env` keeps working. They only take effect when `LLM_LIVE_ENABLED` is true.

## Cost and safety

- A turn costs at most two model calls (extraction, then reply). Greetings and thanks cost none. The shared hourly cap (`LLM_MAX_CALLS_PER_HOUR`) counts every call, retries included, and its refusal degrades to the plain reply.
- Keys stay on the backend. The browser never receives a key, and the OpenAI SDK is still imported only in `app/llm/openai_transport.py`.
- Everything the model is shown (the traveller's message, history, provider text) is data inside a delimited block, and the model is told never to follow it.

## Consequences

- The chat can answer small talk and questions in context and can show labelled MOCK options and weather, but the data is still MOCK. No live provider has been added (ADR 0005, ADR 0006 stand).
- `docs/openapi.json` gained `history` on the request and `intent` on the response.
- Not verified here: the quality of the real model's wording and its Hindi and Hinglish reading, and the OpenAI adapter against the live API beyond the owner's own smoke run. Tests use a scripted fake model and a faked SDK.
- Reply wording is the model's, so an occasional fallback to the plain reply is expected and by design.
