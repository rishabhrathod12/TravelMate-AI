# ADR 0008: Live spoken conversation through OpenAI Realtime

Status: **Accepted by the project owner on 2026-11-03.** Supersedes ADR 0002 decisions 3 and 7 for the first real voice implementation. Related: ADR 0001 (approved stack, the one OpenAI SDK module), ADR 0002 (voice architecture), SECURITY section 12, PRD A28.

## Context

The voice screen has only been a labelled scripted stand-in: no microphone, no sound, no model. The owner asked for real voice through OpenAI and chose the Realtime API (speech to speech) over a speech-to-text, model, text-to-speech pipeline, and approved using the already-declared `openai` package.

ADR 0002 decision 3 made a pipeline the first real implementation and allowed a realtime provider "later, only behind the same interface and only with server-side enforcement of tools and session configuration". Decision 7 required an owner-approved Hindi and Hinglish test before choosing a vendor. This ADR records that the owner has chosen differently.

## Decision

1. **The browser connects to OpenAI directly over WebRTC.** Microphone audio does not pass through this server. This is the "short-lived, narrowly scoped token minted by the backend" option of ADR 0002 decision 4.
2. **The backend mints a short-lived client secret** with `POST /v1/realtime/client_secrets`, through the OpenAI SDK in `app/llm/openai_transport.py`, still the only module that imports it. The real key stays on the server, is read only from `OPENAI_API_KEY` in the environment, and is never put in a response, an error or a log.
3. **The session is fixed on the server when the secret is minted:** model, voice, transcription model, instructions, output-token limit and an empty tool list. The browser sends nothing that changes them.
4. **No tools.** The assistant can talk and cannot search, book, reserve, pay or approve. Planning, quotes and approval stay on screen. Voice recognition is never authorisation.
5. **Owner switch and limits.** Live voice needs `VOICE_LIVE_ENABLED=true` in addition to `VOICE_ENABLED=true` and a key, with every value set explicitly (no hidden defaults), an hourly cap on minted secrets, and the existing per-owner session limits. A key alone never starts a session. Refused in production.
6. **Privacy.** Microphone audio goes to OpenAI while a session is open. The interface says so before the first session. Raw audio is not stored here.
7. **Tests never use the network or a real key.** A fake minter stands in; the real call is checked by the owner by hand.

## Residual risk (stated, not hidden)

- **The browser can try to change the session.** A client holding the secret can usually send its own session updates, for example different instructions. The server cannot stop that when audio goes browser to OpenAI directly, so decision 3 fixes the starting settings, not the whole session. Mitigations: no tools exist to abuse, the secret is short-lived, the minting rate and the number of sessions are capped, the API is development-only with a single configured principal, and the owner's spend is capped in the OpenAI dashboard. If this is not acceptable, the alternative is a server relay (ADR 0002 decision 4, first option), which keeps the configuration under server control at the cost of more code.
- **Session length is enforced by the browser and by OpenAI's own limit,** not by this server, because the audio does not pass through it. The server-side voice session still ends at its time limit and refuses new secrets afterwards.
- **Not verified against the live service by the project:** the exact request fields, the secret's lifetime and the model and voice names were read from OpenAI's documentation and the installed SDK's types, not exercised. The owner's first live run is the test.
- **Hindi and Hinglish quality is untested** (ADR 0002 decision 7). It is recorded as an open assumption in PRD A28.

## Consequences

- New module `app/llm/realtime.py`, a minter in `openai_transport.py`, a route `POST /api/v1/voice/sessions/{id}/realtime` mounted only when live voice is on, and eight new settings.
- The architecture rule "only `openai_transport.py` imports the OpenAI SDK" still holds.
- `VOICE_ENABLED` and `VOICE_LIVE_ENABLED` both stay off by default.
