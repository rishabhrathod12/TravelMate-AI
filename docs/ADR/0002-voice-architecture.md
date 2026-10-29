# ADR 0002 — Voice assistant architecture

Status: **ACCEPTED on 2026-10-29** by the project owner (decision D9 in `docs/VOICE_ASSISTANT_PLAN.md`), as
drafted in milestone V1. Decision point 7 stands: no vendor is selected by this ADR. Evidence:
`docs/VOICE_PROVIDER_EVALUATION.md`.

## Context

Voice is new scope: `docs/PRD.md` has no voice requirement and ADR 0001 approves no voice or realtime provider.
`LLMClient` is text-only, has no assistant turns, no tools field and no streaming. SECURITY §1, §3, §4 and §7 apply
to any voice design.

## Proposed decision

1. Voice is added as an optional layer on top of the existing planning flow. It adds no new authority: it uses
   the same validation, tools, provenance rules and approval path as the text flow.
2. The frontend depends on a `VoiceAdapter` interface; the backend on a `VoiceSession` service. No vendor SDK or
   URL appears outside the adapter implementations (same rule as ADR 0001 for the LLM SDK).
3. First real implementation: a **pipeline** (speech-to-text, `LLMClient`, text-to-speech) behind that interface.
   A realtime speech-to-speech provider is allowed later only behind the same interface and only with
   server-side enforcement of tools and session configuration.
4. The browser never holds a permanent key. It receives either nothing (backend relay) or a short-lived,
   narrowly scoped token minted by the backend.
5. No voice component may import `booking/`, and voice cannot create or confirm an approval or booking.
   Voice recognition is never authorisation. An architecture test enforces the import rule.
6. Raw audio is not stored by default. Transcripts follow the log rules in SECURITY §9.
7. Specific vendors are **not selected** by this ADR. A vendor choice needs a follow-up ADR after an
   owner-approved Hindi/Hinglish test.

## Consequences

- `LLMClient` will need an extension for conversational turns (decision D5, milestone V6).
- PRD needs a voice requirement (wording proposed in the evaluation §6).
- SECURITY needs a short voice section when V3 starts (audio, microphone consent, retention).
- Tests use fake adapters and fake transports; real audio is checked manually.

## Alternatives considered

Realtime speech-to-speech first (lower latency, but bypasses `LLMClient` controls); browser-native speech only
(free, but limited browser support and unknown Hinglish quality). See the evaluation for details.
