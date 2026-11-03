# ADR 0011: Natural conversation, one policy for chat and voice, and relative days as confirmed proposals

Status: **Accepted by the project owner on 2026-11-03** (the owner approved the audit report and phases 0 to 4). Refines ADR 0004 (relative dates), ADR 0009 (replies written with a real model) and ADR 0010 (language policy). Related: ADR 0008 (live voice), SECURITY section 3 and section 12.

## Context

The owner still saw English replies to Hindi voice and Hinglish typing, simple Hinglish not understood, robotic wording, and unreliable context. An audit found:

1. **Both running backends predated the earlier fixes.** Neither had `--reload`, so the voice instructions, turn detection and language policy had never reached a session.
2. **Typed chat was a form with a model attached.** The model read details (without the conversation) and could only reword a question that code had already chosen. Dates accepted only explicit day and month, so "Saturday ko", "kal" and "Sunday" gave nothing. Intent was guessed by regexes that read "Hotel nahi chahiye" as a transport question and "Mera budget 10000 hai" as a cost question. A second preference replaced the first and was reported as a "change".
3. **Voice and typed chat were two engines with two prompts.**
4. **Voice transcription settings were not matched to the model.** The `prompt` hint was sent to `gpt-live-transcribe`, which the SDK documents as taking `languages` and `keywords` instead. (Checked against the installed SDK's types, not the live service.)

## Decision

1. **Relative days are proposals, never facts.** A weekday name ("Saturday ko"), "today/aaj", "tomorrow/kal", "day after tomorrow/parso" and a bare or Hinglish weekend ("weekend par", "is weekend", "agle weekend") are worked out by code from today's date and shown back for a yes or no, exactly as "this weekend" already was. Nothing is used until the traveller confirms. Two different phrases, "next Friday", and any message about returning ("wapas") give no proposal, so the traveller is asked for an exact date. "The weekend" and "every weekend" name no weekend. This refines ADR 0004, which gave nothing for relative words; the rule that code decides the date and the traveller confirms it is unchanged.
2. **The extraction step sees the recent conversation** (the same trimmed history the reply writer sees). It is for understanding what a short message refers to only: a detail is still accepted only if the traveller's current message supports it with a quote, so a detail that appears only in the history is rejected.
3. **The prompt teaches informal Indian speech** (Hinglish, Devanagari, mixed) and defines each intent, including that a budget or a "no" is a preference, not a question. The model still never reports `BOOK_REQUEST`; code finds that itself.
4. **Code fallbacks stop misreading:** a clause that says no ("nahi", "no", "without", "bina") is not used to guess a question; a budget statement is not a cost question; "expensive" alone is not one.
5. **Preferences add up.** A new statement is appended to the earlier ones (up to 300 characters, then the newest is kept alone) and is never reported as a change of the first. No new domain field is added: a budget or a "no hotel" is stored as the traveller's own words and is not used to filter anything, and the reply says so rather than implying it.
6. **Reply writing is more natural but no less checked.** The model is told to react to what was just said, to word the required question in its own way, not to repeat itself, never to say or suggest it searched unless there are facts, and to say honestly when it does not have something. Code still decides what must be asked, still fetches the only facts, and still rejects wording with a new number, a booking or payment claim, a dropped date, or the wrong language, falling back to the catalog sentence. Numbers from the conversation so far (both sides) may be referred to again, so "pehle wale option ka price" can repeat a price an earlier checked reply gave. The history comes from the browser, so this lets a traveller get back only numbers they supplied themselves.
7. **The traveller can ask for a language.** "Hinglish mein baat karo", "explain in English", "Hindi mein" (answered in Roman Hinglish unless Devanagari is written or named) override how the message itself is written, and the choice holds for short answers that follow.
8. **One policy text for chat and voice.** `app/llm/language_policy.py` holds the language, tone and example text. The voice `INSTRUCTIONS` and the chat reply prompt are both built from it.
9. **Transcription settings follow the model.** `gpt-live-transcribe` and `gpt-transcribe` get `languages: ["en", "hi"]`; `gpt-4o` transcribe models (not diarize) get the text hint; other models get neither. No single fixed language is ever set.
10. **No second engine, no workflow change, no new domain fields, no booking path.** `BOOKING_ENABLED` stays false.

## Residual risk and open assumptions

- **The quality of Hindi and Hinglish speech, and of `gpt-4.1-mini` on informal Hinglish, is untested.** Only the owner's listening and reading of live outputs can show it. Voice replies in the right language cannot be verified offline.
- **A relative word is read in the most common way** ("kal" as tomorrow, a weekday as the next one). Because the traveller must confirm, a wrong reading costs one question, not a wrong trip.
- **Hinglish detection stays a word-list heuristic.** The explicit-request rule and the earlier-message rule limit the harm.
- **Voice still cannot see the draft, the facts or the options on screen.** It is a separate engine, by ADR 0008 decision 4 (no tools). A read-only bridge to the chat endpoint would need a new ADR and the owner's approval and is not part of this decision.
- **More model freedom means more rejected wording.** A rejected reply falls back to the catalog sentence, so the traveller still gets a correct, if plainer, answer.
- **Devanagari sentences in the catalog are the developer's own translation** and need a Hindi speaker's review.
- **The `languages` field and the choice of models are checked only against the installed SDK's types.** The first live run is the test.

## Consequences

- New `app/llm/language_policy.py`. Changed: `realtime.py`, `conversation/{dates,draft,intents,claims,manager,reply_writer,language}.py`, `api/chat.py`, `docs/openapi.json` (the pending-date phrase list grew).
- New and updated tests: `test_conversation_natural.py` (the ten requested conversations and the guards around them), `test_conversation_weekend.py`, `test_conversation_manager.py`, `test_conversation_stand_in.py`, `test_chat_api_weekend.py`, `test_realtime_voice.py`.
