# Voice provider and architecture evaluation (V1)

Status: **Draft, research only.** Written 2026-10-29. No account was created, no key was used, and no paid or
live API call was made. Everything here came from public documentation pages read through a web fetch tool, which
summarises the page; treat each figure as "as read on 2026-10-29" and re-check before budgeting or building.
Anything marked **not stated** was absent from the page I read, which is not the same as unsupported.
Part of `docs/VOICE_ASSISTANT_PLAN.md`. Nothing here is a decision.

## 1. Requirements that decide the choice

From the plan and existing docs:
1. Hindi, Hinglish (code-mixed Hindi and English) and English, spoken and heard.
2. Natural turn-taking and interruption (barge-in).
3. No permanent provider key in the browser (SECURITY §1).
4. The model must not invent figures or call arbitrary tools; spoken approval never authorises booking
   (SECURITY §3, §4).
5. Tests run without network, a microphone or keys (NFR-04); provider code sits behind an interface.
6. Cost caps per session and per day (NFR-09); no unnecessary audio storage (SECURITY §7).
7. Provenance (LIVE / CACHED_LIVE / MOCK) must survive into what is spoken.

## 2. Findings by candidate

### 2.1 OpenAI Realtime API (speech-to-speech)
Sources: [Realtime guide](https://developers.openai.com/api/docs/guides/realtime),
[client secrets reference](https://developers.openai.com/api/reference/resources/realtime/subresources/client_secrets/methods/create),
[pricing](https://developers.openai.com/api/docs/pricing), [data controls](https://developers.openai.com/api/docs/guides/your-data).
- Browser connection: WebRTC to `/v1/realtime/calls`; WebSocket is for trusted servers.
- Browser auth: backend calls `POST /v1/realtime/client_secrets` with the real key and hands the browser a
  short-lived secret. TTL default 600 s, range 10 to 7200 s. The secret is **not single use** (it can start several
  sessions until it expires) and session settings attached to it **can be overridden by the client**. So server-side
  enforcement of tools and instructions must not rely on the browser.
- Tools: function calling supported; tools are declared in the session config.
- Models seen on the pricing page: `gpt-realtime-2.1`, `gpt-realtime-2.1-mini`, `gpt-realtime-2`, `-1.5`, `-mini`.
  Audio per 1M tokens: full models $32 in / $64 out; mini models $10 in / $20 out. Live transcription
  `gpt-live-transcribe` and `gpt-realtime-whisper` $0.017 per minute. A `gpt-live-1` voice session is listed at
  $0.05 per minute (billing detail not read).
- Languages: **not stated** on the guide I read. Hindi and Hinglish quality is unverified.
- Maximum session length: **not stated**.
- Data: API data not used for training by default; abuse-monitoring logs kept up to 30 days; Realtime is listed as
  eligible for Zero Data Retention (needs OpenAI approval).
- A developer-forum thread dated 2026-09-09 reports a server "sideband" WebSocket failing (404) when the call was
  made with an ephemeral key. Unconfirmed by official docs; matters if tools run server-side.
- Fit: lowest latency and built-in interruption, but it bypasses `LLMClient`; our prompt-injection controls,
  figure rules and tool allow-list would have to be re-implemented around the session.

### 2.2 Google Gemini Live API (speech-to-speech)
Sources: [capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities),
[ephemeral tokens](https://ai.google.dev/gemini-api/docs/ephemeral-tokens), [pricing](https://ai.google.dev/gemini-api/docs/pricing).
- Models named: `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`, and a legacy Gemini 3.1 Flash Live Preview.
- Languages: 99 listed with BCP-47 codes, **Hindi (`hi`) listed**. Hinglish/code-switching: **not stated**; the page
  only says native-audio models "can switch between languages naturally". Needs a real test.
- Barge-in via voice activity detection, with an `interrupted` flag; input and output transcription available.
- Audio: 16 kHz 16-bit PCM in, 24 kHz out. Audio-only sessions limited to **15 minutes** (extendable with session
  management, not detailed).
- Tools: function calling per model (3.8 Live supports asynchronous calls; Extended Thinking only non-blocking;
  3.1 Flash Live sequential only).
- Browser auth: server-to-server by default; for browsers use ephemeral tokens, which are in **Preview** and work
  only with the Live API on `v1beta`. Defaults: 1 minute to start a session, 30 minutes to send messages; `uses: 1`
  is available; the model and settings can be locked server-side. The page warns tokens can still be extracted from
  client code, so backend authentication matters.
- Price (standard paid tier): audio in $3.00 per 1M tokens (about $0.005/min), audio out $12.00 (about $0.018/min);
  a free tier is listed. Free-tier data-use terms were not read.
- Fit: Hindi listed, cheaper per minute than the OpenAI full models, and ephemeral tokens can lock configuration.
  Preview status and the session limit are risks. Same `LLMClient` bypass as 2.1.

### 2.3 Pipeline: speech-to-text, then `LLMClient`, then text-to-speech
Candidate components, all read from vendor pages unless stated:
- **Sarvam** ([pricing](https://docs.sarvam.ai/api/pricing.md)): STT real-time and batch ₹0.49 per minute (pay-as-you-go,
  excluding GST); TTS Bulbul v4 Flash ₹1.00 and Bulbul v3 ₹3.00 per 1,000 characters; ₹100 free credit per verified
  user. Language list, Hinglish handling and audio retention for STT: **not confirmed from an official page** (one
  vendor voiceover page says its TTS accepts Hindi and Hinglish text; a third-party blog claims better code-mixed STT,
  not independent evidence).
- **Azure Speech** ([language support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support)):
  `hi-IN` is listed for speech to text (including multilingual refinement, preview) and for text to speech (Standard
  and Neural HD voices). An Azure LLM Speech model "automatically detects the languages in your audio"; Hindi-English
  mixing specifically is **not stated**. Real-time Hindi support was not explicit on the part of the page I read.
- **ElevenLabs** ([speech to text](https://elevenlabs.io/docs/overview/capabilities/speech-to-text)): Hindi in the
  "High Accuracy" band, a real-time model (~150 ms), language detection; code-switching **not mentioned**; billed
  per hour of audio including silence. Text-to-speech Hindi coverage came only from third-party sources.
- **Deepgram**: only third-party sources found; its text-to-speech reportedly lacks Hindi. Not recommended for
  evaluation unless that changes.
- Fit: every stage is replaceable and fakeable; `LLMClient` keeps its controls; transcripts are first-class and
  easy to log safely. Costs: latency, several vendors to review, and `LLMClient` needs assistant turns and probably
  streaming (decision D5 in the plan).

### 2.4 Browser-native speech (Web Speech API)
Source: [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).
- MDN marks speech recognition as **limited availability** (not Baseline). In Chrome, recognition is server-based:
  audio goes to a web service. `lang` takes BCP 47 tags such as `hi-IN`; whether a browser actually recognises
  Hindi depends on the engine, and `SpeechRecognition.available()` (experimental) can check at runtime.
- On-device recognition (`processLocally`) is experimental.
- Fit: zero extra cost and no key, so suitable for the V2 prototype and as a degraded mode, not as a guaranteed
  production path. Hinglish quality unknown.

## 3. Comparison

| Criterion | A. Realtime S2S (OpenAI) | A. Realtime S2S (Gemini) | B. Pipeline | C. Browser-native |
|---|---|---|---|---|
| Hindi | Not stated | Listed | Depends on parts; Azure listed, others unconfirmed | Browser-dependent |
| Hinglish | Unverified | Not stated | Unverified | Unverified |
| Barge-in | Yes (realtime) | Yes (VAD) | Must build | Limited |
| Passes through `LLMClient` | No | No | Yes | Text only, yes |
| Browser auth | Ephemeral secret, overridable | Ephemeral token (Preview), lockable | Backend relay or per-stage keys | None needed |
| Tool control | Provider-side session | Provider-side session | Our code | Our code |
| Indicative audio cost | $32/$64 per 1M tokens (full) | about $0.005 in, $0.018 out per min | Sarvam about ₹0.49/min STT + TTS per 1,000 chars | Free |
| Audio leaves our control | Yes | Yes | Yes (per vendor) | Often (Chrome) |
| Test without network | Fake transport | Fake transport | Fake per stage | Fake adapter |

## 4. Recommendation (for your approval)

1. **Keep the architecture provider-neutral.** Define a `VoiceAdapter` on the frontend and a `VoiceSession` service on
   the backend; the product depends on the interface, never on a vendor.
2. **V2 prototype uses a mock adapter, plus optionally the browser-native adapter** (option C) for local manual tries.
3. **Production default: option B (pipeline)** for the first real implementation, because it keeps the existing
   `LLMClient` controls (data blocks, typed outputs, no tools, figures from code) and the tool allow-list in our
   code. Option A stays a documented later option if latency proves unacceptable, but it must then run behind an
   enforcement layer (tools executed by our backend only, session config set server-side and not trusted from the
   client, no approval or booking tool).
4. **Hindi/Hinglish decision needs a test, not a document.** Before choosing STT/TTS vendors, run a small,
   owner-approved listening test with the same scripted phrases. That test needs a key and uses paid or free-tier
   credit, so it is **not done** and waits for your approval.
5. Shortlist for the test (your approval needed, D4): Azure Speech, Sarvam, ElevenLabs for the pipeline; Gemini
   Live and OpenAI Realtime for option A.

## 5. Unknowns that must be answered before building

- Hindi and Hinglish accuracy for each shortlisted vendor (needs a real audio test).
- OpenAI Realtime language list and maximum session length; Gemini free-tier data terms.
- Whether ephemeral-key sideband tool handling works for OpenAI (forum report only).
- Sarvam language list, code-mixed STT and audio retention from an official page.
- Latency measured from India, not a vendor figure.
- Whether the owner has, or will supply, any vendor account (D-new: who supplies keys and who pays).

## 6. Proposed PRD wording (not applied to `docs/PRD.md`)

- New requirement FR-17 (Should): "The user can hold a spoken conversation with the planner in Hindi, Hinglish or
  English. The spoken flow uses the same planning tools, validation and provenance rules as the text flow, offers a
  text fallback, and cannot approve or execute a booking."
- New non-functional note: audio is not stored by default, third-party audio processing is disclosed, and usage is
  capped (NFR-09).
- Mark voice as Out of MVP until its milestones pass. Apply only after you approve the wording.

## 7. Source reliability

Official vendor pages: OpenAI, Google, Microsoft, Sarvam pricing, ElevenLabs capability page, MDN. Third-party blogs
and a developer forum were seen in search results but are not relied on except where stated as unconfirmed.
The fetch tool summarises pages, so exact thresholds and wording should be re-read at the source before any
purchase or build decision.
