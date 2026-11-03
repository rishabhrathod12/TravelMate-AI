# ADR 0010: Voice turn-taking and one language policy for typed chat and voice

Status: **Accepted by the project owner on 2026-11-03** (the owner approved the inspection plan and phases 1 to 3; this ADR is phase 4). Related: ADR 0008 (live voice), ADR 0009 (chat replies with a real model), ADR 0002 (voice architecture, decision 7 on Hindi and Hinglish), SECURITY section 12, PRD A28 to A30.

## Context

Two problems were reported.

1. **The voice assistant answered before the person finished.** Verified: `session_settings()` in `app/llm/realtime.py` set no `turn_detection`, so the session ran on OpenAI's own default. Our reading of that default (not checked against the live service) is voice-activity detection with a very short silence, which a normal pause to think exceeds. The browser adapter also showed "thinking" the moment speech stopped, and a typed message could ask for a reply while one was already running.
2. **Hinglish input got English replies.** Verified: every fixed sentence code writes (questions, date confirmation, read-back, errors, the can't-book notice, the MOCK footer) was English; only small talk had a Hinglish version. The reply writer was told to use the traveller's language, but it was also told to say what an English plain reply says, it was skipped for small talk and unclear input, its output was dropped whenever it failed the number check, and language was detected nowhere except for small talk. With live calls off, the English-only stand-in reader and English plain replies were all the traveller saw. The frontend payload and history were correct.

## Decision

### Voice turn-taking

1. **Turn detection is set on the server when the secret is minted.** `audio.input.turn_detection` is part of `session_settings()`. Default: `semantic_vad` with `eagerness: low`, so the provider judges whether the sentence is finished instead of timing a silence. Alternative: `server_vad` with a fixed `silence_duration_ms` (default 1500). Both set `create_response: true` and `interrupt_response: true`: a reply starts by itself when the turn ends and is cancelled if the person speaks again.
2. **Configurable, with named defaults.** Optional settings `VOICE_TURN_MODE` (`semantic` or `server`), `VOICE_TURN_EAGERNESS` and `VOICE_TURN_SILENCE_MS` (300 to 10000). Blank uses the defaults in `app/llm/realtime.py`, the same pattern as the reply caps in ADR 0009. Bad values are refused when the settings load.
3. **No extra fixed delay on top of the provider.** A longer silence makes every reply slower; the semantic mode keeps answers quick when a sentence is plainly complete.
4. **The browser adapter shows one reply at a time.** "Thinking" appears when a reply starts, not when speech stops. Leftovers of a reply the person talked over are dropped. A typed message sent during a running reply waits and asks once when it finishes, so no duplicate reply is requested.
5. **Nothing here widens what the assistant can do.** No tools, no booking, no approval. `BOOKING_ENABLED` stays false.

### One language policy

6. **Reply in the language and script of the traveller's latest message:** English gets English, Hindi in Devanagari gets Hindi, Roman-script Hindi gets casual Roman-script Hinglish (not formal Hindi). A message with no clear signal (a date, a place name, a number) keeps the language of the traveller's earlier messages. A switch of language switches the reply. Names, places, dates and numbers are never translated. Common travel words (flight, hotel, weekend, weather) stay as they are.
7. **Typed chat.** `app/conversation/language.py` detects the language with word lists in plain code (no dependency, no model call) and holds one catalog of every fixed sentence in the three languages. `POST /chat/turns` resolves the language from the message and the traveller's earlier messages and passes it through `ConversationManager.handle` and `compose`. The reply writer is told `reply_language`, shown Hinglish style examples, and its output is rejected if it is plainly in another language (`reply_fits_language`); the catalog sentence in the right language is shown instead. The number, booking-claim and read-back checks of ADR 0009 are unchanged. Detection is a hint, not a verdict.
8. **Voice.** The fixed `INSTRUCTIONS` state the same policy and ask the assistant to let an unfinished sentence continue. The transcript hint (`audio.input.transcription.prompt`) names English, Hindi and Hinglish without forcing one. No `language` is set on transcription, because a fixed language would mis-transcribe Hinglish and a mid-conversation switch.
9. **No second conversation engine, no change to the LangGraph workflow.** The workflow still asks its questions in English (`QUESTIONS`).

## Residual risk and open assumptions (stated, not hidden)

- **Not verified against the live service:** the `turn_detection` field names and values, `semantic_vad` support for the chosen model, and the `transcription.prompt` field were taken from memory of OpenAI's API, not from the SDK (not installed in the environment used for this work) and not exercised. If the provider rejects a field, session creation fails; removing that field is the fix. The owner's first live run is the test.
- **The final `eagerness` and silence values are not decided.** The defaults are a starting point. The owner's manual test (a sentence with a 1 to 2 second pause, a trailing "umm", talking over a reply, Hinglish, a mid-session language switch) sets them.
- **Hinglish and Hindi quality, speech and transcript, remains untested** (ADR 0002 decision 7, PRD A28). A speech-to-speech model hears the audio directly, so a wrong transcript does not prove the model misheard.
- **The browser can still change its own session,** including turn detection (ADR 0008, residual risk). It affects the experience only; there are no tools.
- **Language detection is a keyword heuristic.** Short or mixed messages can be misread. The model's own reading and the fallback to catalog sentences limit the harm. Bare "haan" or "nahi" count as no signal.
- **The Devanagari catalog sentences are the developer's own translation** and need a Hindi speaker's review.
- **The development stand-in reader is English only.** With `LLM_LIVE_ENABLED` off, a Hinglish message gets the right reply language but its details (for example "Indore se Goa") are not extracted.
- **Trip summaries keep their details as given** (for example English month names), by design.
- A longer silence threshold makes the assistant slower; false speech starts from background noise may need noise reduction (not enabled).

## Consequences

- `app/llm/realtime.py` (turn detection, instructions, transcript hint), three optional settings in `config.py`, `main.py` and `.env.example`; `frontend/src/voice/realtimeAdapter.ts`.
- New `app/conversation/language.py`; `draft.py`, `intents.py`, `manager.py`, `reply_writer.py` and `api/chat.py` take a language. `manager.handle` and `compose` default to the message's own language when none is passed.
- Two existing manager tests now pass `"en"` explicitly, because a Hinglish message is now answered in Hinglish.
- A new unit test file, `tests/unit/test_conversation_language.py`, and new voice tests.
