# TravelMate AI — Voice Assistant Plan

Status: **Draft v0.1, awaiting owner approval.** Nothing in this plan is implemented. This file is the permanent
record for the voice-assistant work. Future sessions start from **§13 NEXT ACTION**.

Naming: voice milestones are **V0–V12** so they cannot be confused with the core milestones **M0–M14** in
`docs/IMPLEMENTATION_PLAN.md`. (Decision D1 in §10: say if you want the `M` prefix instead.)

Facts are split into **Verified** (read from the repository on 2026-10-29 in this session) and **Reported**
(carried over from earlier documents or messages, not re-checked). Do not promote a reported item to a fact
without checking it.

---

## 1. Goal and expected experience

Natural two-way voice conversation in Hindi, Hinglish and English (to the extent the chosen provider supports
them; unverified until V1):

> User: "Mujhe Indore se Goa jana hai. Saste options batao."
> Assistant (aloud): "Bilkul! Aap kis date ko travel karna chahte hain?"
> User answers by voice; the assistant keeps context, asks follow-ups, then researches options, compares
> transport and hotels, estimates cost, drafts an itinerary and explains the findings aloud.

The assistant answers questions in voice. It is not a speech-to-form-field converter. A text fallback is always
available. While only mock providers exist, every spoken and written result says it is MOCK data.

## 2. Current verified repository state (2026-10-29)

Verified:
- Branch `main`, clean tree, in sync with `origin/main` at `0ad3730`. M6 (`803f9d6`) is pushed.
- Backend `backend/app/`: `api/` (only `health.py`), `domain/`, `providers/` (interfaces + MOCK only), `tools/`
  (research, comparison, recorder), `llm/` (M6), `config.py`, `main.py`. **Not present:** `workflow/`,
  `services/`, `persistence/`, `booking/`, and any `voice/` or conversation code.
- The only real HTTP route is `GET /health` (plus FastAPI's `/docs`). No sessions, no WebSocket, no auth.
- `LLMClient` (`app/llm/base.py`, `types.py`): request/response only. `LLMMessage.role` allows only `system` and
  `user` (no assistant turns). There is deliberately **no tools field** (SECURITY §3.3). No streaming, no audio.
  Limits (`max_output_tokens`, `timeout_seconds`) have no defaults. Only `FakeLLMClient` and an OpenAI adapter
  with an injected transport exist; the adapter has **no real transport**, and `pyproject.toml` has no `openai`
  or `langgraph` dependency.
- `app/llm/drafter.py` produces an `Itinerary` from selected options; no code extracts a `TripRequest` from
  free text or dialogue.
- Frontend (`frontend/`): React 19.2.9, Vite 8, TypeScript 6, Vitest. Dependencies are only `react` and
  `react-dom`: no audio, WebSocket or realtime library. Source layout: `src/api/health.ts`, `components/`
  (including `TripForm.tsx`, `OptionCards.tsx`, `CostBreakdown.tsx`, `ItineraryView.tsx`, `ApprovalPreview.tsx`,
  `DemoBanner.tsx`), `views/` (`PlanTripView`, `MyTripsView`, `AboutView`), `lib/`, `demo/demoData.ts`,
  `contracts/types.ts`. All displayed trip data is hand-written demo data labelled MOCK.
- `docs/PRD.md` has **no voice, speech, audio or language (Hindi/Hinglish) requirement**. The MVP scope lists a
  web UI for planning only. `docs/ADR/0001-approved-stack.md` approves LangGraph and OpenAI-behind-`LLMClient`
  only; it contains no voice or realtime provider.
- `README.md` does not exist.
- Last results run this session: backend 1084 tests passed (Python 3.12.10); `ruff check`, `ruff format --check`
  and strict `mypy app` clean at `803f9d6`. Not re-run since: frontend tests, lint, typecheck, build.

Reported (not re-checked): CI passed for the M6 push (owner's report); frontend had 142 tests at `b950e13`;
the frontend has never been viewed in a browser.

Consequence: **voice is new scope.** Under `CLAUDE.md`, adding it needs a PRD scope amendment and an ADR for any
new provider or transport. This plan does not make those decisions (see §10).

## 3. Architecture options (nothing selected)

Provider facts below are **unverified** and are to be checked against official documentation in V1.

| Option | Shape | Strengths | Risks / open points |
|---|---|---|---|
| A. Realtime speech-to-speech | Browser connects to a realtime model service (WebRTC or WebSocket) using a short-lived token minted by our backend. | Lowest latency, natural interruption. | Does not pass through `LLMClient`; tool calling and "no invented figures" must be enforced outside the model; paid; audio goes to a third party; language support unverified. |
| B. STT + LLM + TTS pipeline | Browser streams audio (or text) to our backend; backend runs speech-to-text, `LLMClient`, then text-to-speech. | Reuses `LLMClient` and its injection controls; each stage replaceable and fakeable; transcript is first-class. | Higher latency; barge-in is harder; `LLMClient` needs assistant turns and (maybe) streaming; three providers to price and review. |
| C. Browser-native speech (Web Speech API) | Browser does recognition and synthesis; only text reaches the backend. | No audio leaves our control (browser vendor may still process it); no cost; good for the V2 prototype. | Browser support and Hindi quality vary and are unverified; not a production-grade guarantee. |

Likely direction, to be confirmed in V1 and then approved: **C for the prototype, B or A for production**, with the
voice layer behind a `VoiceAdapter` interface so the choice stays swappable.

## 4. System architecture and responsibilities (target)

```
Browser: VoicePanel (state machine, transcript, text fallback)
   │  VoiceAdapter (mock | browser-native | provider)
   ▼
Backend: voice session service ── conversation manager ──► TripRequest builder (validates via domain)
   │ (short-lived session, expiry, limits)        │
   │                                              ▼
   │                                   LLMClient (text) / planning workflow (later)
   ▼
Approved typed tools only: search_transport, search_hotels, get_weather, compare, cost, itinerary
```

| Component | Responsibility | Must not |
|---|---|---|
| `VoicePanel` + voice state machine (frontend) | States idle / listening / thinking / speaking / interrupted / error; transcript; text fallback; labels MOCK. | Hold a permanent provider key; claim real audio intelligence in mock mode. |
| `VoiceAdapter` (frontend) | One interface over mock, browser-native and provider transports. | Contain business rules. |
| Voice session service (backend) | Creates short-lived sessions, enforces expiry, rate and cost limits, mints provider tokens (if option A). | Persist raw audio by default; expose permanent keys. |
| Conversation manager (backend) | Holds in-session context, extracts structured trip details, asks for missing ones. | Invent dates or other critical fields; skip domain validation. |
| Tool layer | Calls only approved typed tools; keeps provenance. | Expose booking, approval or arbitrary tools; fabricate tool results. |
| Booking | Untouched. Disabled. | Be importable from `voice/` (architecture test). |

Dependency rules to add (architecture test, like the existing ones): `voice/` must not import `booking/`; voice
transport code must not import workflow internals; the frontend voice code must not read provider keys.

## 5. Roadmap

| ID | Milestone | Depends on | Needs your approval before starting |
|---|---|---|---|
| V0 | Repository audit and voice requirements | none | no |
| V1 | Architecture and provider evaluation (research only) | V0, D1–D3 | web research; no paid calls |
| V2 | Voice interface prototype (mock adapter) | V1 | frontend work only |
| V3 | Voice session and security foundation | V1 | provider/ADR choice; new dependencies |
| V4 | Two-way voice conversation | V2, V3 | live audio provider and any paid use |
| V5 | Conversational context and trip requirements | V4 (can start text-only after V2) | none beyond Q14 |
| V6 | Connect to the existing LLM interface | V5 | any paid model call; Q19 |
| V7 | Agent tool integration | V6, core M4/M5 (done) | tool list |
| V8 | Planning workflow integration | V7, core M7 | langgraph dependency; Q9–Q18 |
| V9 | Spoken response and conversational quality | V4, V7 | none |
| V10 | Security, privacy, reliability, cost controls | V3, V7 | none |
| V11 | Automated testing and acceptance | V2–V10 | none |
| V12 | Documentation and handoff | V11 | none |

Ordering notes: V2 is deliberately before V3 so a UI exists to review. V5 text-only logic does not need audio and
can run in parallel with V3/V4. V8 is blocked by the core planning workflow (core M7), which is itself waiting on
your answers to Q12, Q13, Q14, Q18 and approval of the `langgraph` dependency. **V0–V7 do not need those answers
except Q14 (traveller/text limits) for V5.** Independent components proceed while Q9–Q18 stay open; none of them is
resolved in code.

### Per-milestone scope, files, tests and acceptance

Files are proposals; they are confirmed or changed when each milestone starts.

**V0 — Audit and requirements.** This document is the output. Acceptance: §2 is verified and sourced; open
decisions are listed in §10; no code changed. Test strategy: none (read-only).

**V1 — Architecture and provider evaluation.** Output: `docs/VOICE_PROVIDER_EVALUATION.md` plus a proposed ADR
`docs/ADR/0002-voice-architecture.md` (draft). Read official docs for languages (Hindi/Hinglish/English),
latency, browser security and token model, tool calling, pricing, data retention and privacy for each option and
named provider. Acceptance: each claim cites a source and date; recommendation compares A/B/C against
requirements; no paid call, no account, no key. Waits for your approval of the chosen option.

**V2 — Voice interface prototype.** Files: `frontend/src/voice/voiceMachine.ts` (+ test),
`voice/VoiceAdapter.ts`, `voice/mockAdapter.ts`, `components/VoicePanel.tsx` (+ test), `components/Transcript.tsx`,
`views/PlanTripView.tsx` (mounts the panel), styles. Behaviour: six states, transcript, session controls, text
fallback, a persistent "MOCK voice — no real audio" banner, keyboard operable (NFR-12), works at 375 px (AC-10).
Acceptance: state-machine unit tests incl. illegal transitions; component tests; `npm run lint`, `typecheck`,
`test`, `build` all run and reported. Manual check in a browser recorded as manual.

**V3 — Session and security foundation.** Backend files: `app/voice/session.py`, `app/voice/config.py`,
`app/api/voice.py` (session create / end), settings entries for limits (no secret values in code), tests under
`backend/tests/unit` and `architecture`. Behaviour: short-lived opaque session IDs with expiry, per-session and
per-day limits, microphone permission handling and an in-UI notice that audio is processed by a third party
(if A/B), no permanent key in the frontend bundle. Authentication follows PRD Q4; until then the existing rule
"explicit dev principal, never anonymous by default" applies. Acceptance: expiry, limit and key-leak tests; secret
scan; bundle grep shows no key.

**V4 — Two-way voice conversation.** Files depend on the chosen option (`voice/providerAdapter.ts`, backend
token/relay endpoint). Behaviour: spoken input, spoken output, turn-taking, interruption where supported,
transcripts, Hindi/Hinglish/English as verified in V1, text fallback, clear failure messages. Acceptance:
adapter tested with a fake transport; real-audio behaviour only claimed after your manual test; no paid use
without approval.

**V5 — Conversational context and trip requirements.** Files: `app/voice/conversation.py` (session context),
`app/voice/trip_builder.py` (structured extraction → `TripRequest` candidate), review/edit UI reusing `TripForm`.
Behaviour: remember supplied details, ask for missing ones (FR-15, AC-09), user reviews and corrects before
anything runs, domain validation is final, no invented dates. Acceptance: table-driven tests incl. Hinglish
phrases, missing/ambiguous dates, corrections, one-way vs round trip; extraction tested with `FakeLLMClient`.

**V6 — Connect to the existing LLM interface.** Likely change: add assistant turns (and possibly streaming) to
`LLMMessage`/`LLMClient` backward-compatibly, or a separate conversational interface — decision D5. Acceptance:
fake-client tests only; the OpenAI transport stays unimplemented until approved; no claim a real adapter works
until it has run live with your approval (Q19).

**V7 — Agent tool integration.** Files: `app/voice/tools.py` with typed inputs/outputs wrapping
`search_transport`, `search_hotels`, `get_weather`, comparison and cost estimator; timeouts, bounded retries,
per-session call caps; results carry provenance. Acceptance: model cannot call anything outside the allow-list;
fabricated tool results are rejected; every figure spoken comes from a tool result; AC-04/AC-02-style tests.

**V8 — Planning workflow integration.** Wrap core M7 (LangGraph) behind the voice session; keep voice transport
separate from orchestration; explicit workflow state and recoverable errors. Blocked by core M7 and Q9–Q18.

**V9 — Spoken response quality.** Spoken summaries of options, cost and itinerary; long-answer chunking;
silence, unclear-audio and repeat handling; transcript equals what is spoken; MOCK stated aloud when applicable.

**V10 — Security, privacy, reliability, cost.** Tests for session expiry, authorization, rate limits,
disconnects, provider failure, malformed tool requests, prompt injection through speech and transcript text,
and "spoken approval does nothing". Retention and third-party processing documented. Usage caps wired to
NFR-09.

**V11 — Testing and acceptance.** Run and record: frontend lint, typecheck, test, build; backend pytest, Ruff,
strict mypy. List manual microphone/browser checks (Chrome and at least one other, desktop and 375 px).

**V12 — Documentation and handoff.** `README.md` (does not exist yet), `PROJECT_CONTEXT.md`, this plan; env
variable names only; exact startup commands and URLs; mock vs live table; known limitations.

## 6. Test strategy (all milestones)

- No test needs network, a microphone or a real key. Fakes: `FakeLLMClient`, a scripted `FakeVoiceAdapter`, a fake
  speech transport.
- Real microphone, speakers and live audio are manual checks, recorded as such, never claimed as automated.
- Every milestone reports commands run and actual results, including failures and skips.
- Add architecture tests for the new dependency rules in §4.

## 7. Security, privacy, cost and booking safety

- Booking and payment stay disabled. **A spoken request, a transcript or voice recognition is never authorization
  for a booking, payment or approval.** Approvals stay a separate, visible UI action under SECURITY §4;
  the voice layer has no approval or booking tool.
- Speech and transcripts are untrusted input (SECURITY §3): handled as data, never as instructions.
- No permanent provider key in frontend code, bundles, logs, docs or git. Short-lived tokens or a backend relay only.
- No raw audio storage by default. If any retention is ever needed it needs your approval, a retention period and
  deletion path (SECURITY §7). Logs follow SECURITY §9 (no prompts, no transcripts in full, no audio).
- Third-party audio processing is disclosed to the user before the microphone is used.
- Cost: per-session and per-day caps, session expiry, and counting of provider usage (NFR-09). No paid call or
  account creation without your explicit approval.
- Never present MOCK as LIVE; never invent prices, schedules, availability, weather or booking outcomes.

## 8. Existing constraints that shape the design

- `LLMClient` has no assistant role, no tools field and no streaming; option A bypasses it entirely.
- Itinerary and cost code already refuse to let the LLM produce figures; voice must keep that property.
- PRD Q9–Q18 stay open. Q14 (traveller and text limits) directly affects V5; Q19 affects V6.

## 9. Not covered by this plan

Real bookings, payments, live travel providers (core M13/M14), authentication design (PRD Q4), mobile apps.

## 10. Open questions and decisions awaiting approval

| # | Decision | Recommendation |
|---|---|---|
| D1 | Use `V0–V12` ids instead of `M0–M12`? | **APPROVED 2026-10-29.** |
| D2 | Approve voice as new product scope (PRD amendment) and a new ADR in V1? | **APPROVED 2026-10-29.** ADR 0002 is drafted as PROPOSED; proposed PRD wording is in the evaluation §6 and is **not yet applied to `docs/PRD.md`**. |
| D3 | May V1 browse official provider documentation on the web? | **APPROVED 2026-10-29.** |
| D4 | Provider shortlist for a Hindi/Hinglish audio test | V1 proposes: Azure Speech, Sarvam, ElevenLabs (pipeline); Gemini Live, OpenAI Realtime (realtime). Awaiting your decision. |
| D9 | Approve the V1 recommendation (provider-neutral interfaces; pipeline first; realtime later behind the same interface; ADR 0002)? | Yes, after reading the evaluation. |
| D10 | Who supplies vendor keys and pays for the Hindi/Hinglish test and later use? | Owner. No key has been requested or used. |
| D5 | Extend `LLMClient` with assistant turns/streaming, or add a separate conversational interface? | Decide in V6; do not change `LLMClient` before then. |
| D6 | Priority of Hindi and Hinglish vs English quality if providers differ? | Owner decision. |
| D7 | Core M7 (workflow) was started and paused this session awaiting: `langgraph` approval and Q12/Q13/Q14/Q18. Resume it before, after or alongside voice? | Finish core M7 decisions first; V0–V7 do not depend on it. |
| D8 | Is a typed text-only conversation (V5) acceptable as the first deliverable before any audio? | Yes. |
| — | PRD Q4 (auth), Q9–Q18, Q19 | Remain open; not resolved here. |

## 11. Progress

| ID | Status | Evidence / notes |
|---|---|---|
| V0 | DONE (awaiting your approval of this plan) | §2 verified from the repo on 2026-10-29; no code changed. |
| V1 | DONE as a draft (awaiting your approval of the recommendation) | Research only. `docs/VOICE_PROVIDER_EVALUATION.md` and proposed `docs/ADR/0002-voice-architecture.md` written 2026-10-29. No account, key, or paid/live API call. Hindi/Hinglish quality is NOT verified and needs an owner-approved audio test. No vendor selected. |
| V2 | DONE (awaiting your review; manual browser check not done) | Mock-only prototype in `frontend/src/voice/` and `components/VoicePanel.tsx`, mounted on the Plan page. Run 2026-10-29: `npm run lint`, `typecheck`, `build` pass; `npm test` 203 passed in 13 files (the count before V2 was not re-measured). Not done: viewing it in a real browser, 375 px visual check, screen-reader check, keyboard walkthrough (all manual). No microphone, audio, network or key is used. |
| V3 | NOT STARTED | |
| V4 | NOT STARTED | |
| V5 | NOT STARTED | |
| V6 | NOT STARTED | |
| V7 | NOT STARTED | |
| V8 | BLOCKED | Core M7, Q9–Q18, langgraph approval. |
| V9 | NOT STARTED | |
| V10 | NOT STARTED | |
| V11 | NOT STARTED | |
| V12 | NOT STARTED | |

## 12. Changelog

- 2026-10-29: Plan created (V0). Repository inspected; voice found to be outside the current PRD and ADR scope.
  No voice code written. Not committed.
- 2026-10-29: Owner approved D1, D2, D3. V1 executed as documentation research: wrote
  `docs/VOICE_PROVIDER_EVALUATION.md` and draft `docs/ADR/0002-voice-architecture.md` (PROPOSED). No code, no
  keys, no paid calls. Not committed. Core M7 remains paused.

- 2026-10-29: Owner approved D9. ADR 0002 marked Accepted; FR-17 added to `docs/PRD.md` (priority Could, not MVP).
  V2 built: voice state machine, `VoiceAdapter` interface, mock adapter, `useVoiceSession`, `VoicePanel`,
  `Transcript`, styles. Not committed.

## 13. NEXT ACTION

**Owner reviews V2**: run `npm run dev` in `frontend/`, open http://localhost:5173 and try the voice panel
(start, simulate a phrase, interrupt, error, type a message; also at a narrow width and with the keyboard only).
Then approve committing V2. After that the next milestone is **V3** (voice session and security foundation:
backend session service, expiry and limits). V3 adds backend code and settings but no vendor key; any provider
dependency or token minting waits for your vendor decision (D4, D10).

When you say "continue voice assistant", a session must read `CLAUDE.md`, `docs/PROJECT_CONTEXT.md`, this file,
and the relevant architecture and security docs, then run `git status`, check the code against §2, report the
current milestone, and continue from this section.
