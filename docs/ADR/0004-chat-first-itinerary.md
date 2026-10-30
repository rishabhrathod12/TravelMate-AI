# ADR 0004 — Chat-first itinerary planning

Status: **ACCEPTED on 2026-10-30** by the project owner, who chose the options marked "recommended"
below. Nothing in this ADR is implemented yet.

## Context

The owner wants the product to feel like ChatGPT or Claude: a customer types "plan my 5-day
itinerary for Goa this weekend" and the assistant writes the whole itinerary. They do not want a
traditional flight/train search dashboard as the main screen. The PRD (FR-02 to FR-06) and the
current frontend are built around searching and comparing options first. Three existing rules
also constrain this: `CLAUDE.md` forbids inventing live travel data, the V5 conversation logic
never turns relative words ("tomorrow", "this weekend") into dates, and no real language model
is connected (PRD Q19; the chat runs on a pattern-matching stand-in, SECURITY §13).

## Decision

1. **Chat first.** The conversation becomes the main screen of the app and the way an
   itinerary is requested and presented. The comparison dashboard (transport and hotel options,
   cost, demo booking) is kept but moves behind an optional link; nothing built for M3 to M5 or
   ADR 0003 is removed. This supersedes the "search first" ordering of FR-02 to FR-06 for the main
   flow; those requirements still apply to the optional view.
2. **Relative dates are resolved by code and confirmed by the traveller.** For a short fixed list
   of English phrases (for example "this weekend", "next weekend"), code, never the model,
   computes the exact dates from today's date and the chat shows them back ("Saturday 7 November
   to Sunday 8 November, right?"). No trip is planned until the traveller confirms. Anything
   not on the list is still asked for as an exact day and month. This relaxes, and does not
   remove, the V5 rule. Which day a weekend starts on is fixed in code and tested.
3. **Itinerary content is general suggestion, labelled.** The model may suggest areas, places,
   activities and the shape of each day from its general knowledge. Every such item carries the
   label `AI_SUGGESTION`, shown to the user as "AI suggestion, not verified". It is a separate
   label from the provenance labels `LIVE`, `CACHED_LIVE` and `MOCK`, and is never presented as
   provider data. The itinerary may not state prices, opening hours, availability, travel times,
   weather or booking outcomes as facts. Those appear only from labelled provider or MOCK data
   (the M6 drafter already flags text that seems to state a price, time, date or booking claim).
4. **Stand-in first, real model later.** The chat-first screen and the itinerary flow are built
   and reviewed on the fake model. The stand-in cannot write a real itinerary, so until a real
   model is connected the screen shows a clearly labelled scripted sample, not the model's work.
   Connecting a real model is a separate step that needs, each as its own approval: Q19 (model,
   token limit, timeout, prompt-size limit), the `openai` dependency and a real transport, an
   owner-supplied key in the owner's own shell, and the first live call.
5. **Booking stays off.** The chat cannot book, approve or pay. A spoken or typed "book it" does
   nothing. `BOOKING_ENABLED` stays false and ADR 0003 still applies.

## Amendment: C1 as built (2026-10-30)

- Only two phrases are resolved: "this weekend" and "next weekend". Other relative words
  ("tomorrow", "next Friday", "kal", "in 3 days") are still not dates and the traveller is asked
  for a day and month.
- The phrase resolves to the **Saturday** only, not a Saturday-to-Sunday pair. How long the trip
  lasts decides the last day, so "5 days this weekend" starts on Saturday. The Sunday is never
  assumed. This narrows the example in item 2 above.
- "This weekend" on a Saturday is that day (the reply says "today"). On a Sunday it is not
  resolved and an exact date is asked for. "Next weekend" is the Saturday after "this weekend"'s;
  on a Sunday it is the Saturday six days away. A weekend starts on Saturday in this code.
- The worked-out date waits in the draft (`pending_date`, a fixed phrase and a date) and is used
  only after a plain yes ("yes", "ok", "haan", ...). A no, or any other message, drops it. A
  message that mixes a yes with other words is not agreement. An explicit date in the same message
  wins over the phrase. The model cannot set a date from the phrase (it is refused as before).
- A new turn status, `CONFIRM_DATES`, tells the screen a date is waiting for an answer.

## Amendment: C2 as built (2026-10-30)

- **Itinerary request.** A new `ItineraryRequest` (destination, start date, days; optional head
  count and preferences) is separate from `TripRequest`. Asking for "N days" puts the chat in
  itinerary mode: only the destination and the start date are asked for (PRD A14). 1 to 14 days
  (A15, provisional). Day counts are checked against the traveller's own words like every other
  detail, and a request for more days is refused with an explanation, never silently dropped.
- **Chat first.** In development builds the Plan page opens on the chat ("Where to next?"). A
  button opens and closes the transport and hotel comparison (and voice, demo booking), so
  nothing built earlier is removed. In a production build the page is the old dashboard, because
  the chat runs on a development stand-in and the backend refuses to serve it in production. The
  chat code is absent from the production bundle (checked).
- **Chat and voice are equal (owner request, 2026-10-30).** In the chat-first screen the chat and
  the voice screen ("Talk to TravelMate") sit side by side on wide screens and stacked on narrow
  ones, both visible without opening the comparison. Voice is still the mock or session-only
  adapter: it hears and plays nothing until the voice work (Step C) is approved. Its way-back
  button says "Back to the chat".
- **Scripted sample only.** The "plan" shown for an itinerary request is fixed placeholder text
  (`frontend/src/demo/sampleItinerary.ts`): it names the destination and the shape of each day, and
  no activity, price, time or opening hour. A banner and every line say "Scripted sample". The
  label `SCRIPTED_SAMPLE` is distinct from `AI_SUGGESTION`; nothing carries `AI_SUGGESTION` until a
  real model is connected (C3).
- **Limits.** The chat endpoint now caps travellers at 9 (Q14). The search form's cap of 50 and its
  missing 500-character preferences limit are not changed yet.

## Plan (each phase stops for the owner's review)

- **C1, relative dates:** the fixed phrase list, code-computed dates, a confirmation step in the
  conversation manager, tests that include the day-of-week edge cases (a Saturday or Sunday
  "today"), and a mutation check like the one used for V5.
- **C2, chat-first screen:** the chat becomes the main view with the sample itinerary and the
  `AI_SUGGESTION` label; the dashboard moves behind a link; trip length ("5 days") becomes part
  of the request, subject to the open limits below.
- **C3, real model:** blocked on the approvals in item 4.

## Open items this ADR does not decide

- Trip length limits and what "5 days" means for the number of nights (PRD Q13 already says a
  round trip has nights = return minus departure, and an itinerary of nights + 1 days).
- Where the traveller starts from when they give only a destination.
- Whether to keep a conversation history on the server (today the server keeps nothing).
- Authentication, per-person rate limits and cost counting, required before a real model.

## Consequences

- The product no longer depends on provider search to be useful. It can still be misleading if
  a plan looks authoritative, so the `AI_SUGGESTION` label and the no-facts rule are the main
  safeguards, and a reviewer must check them in the real model step.
- A new label (`AI_SUGGESTION`) is introduced. It must not be added to `Provenance`, which is
  for provider data; it needs its own type when implemented.
- The V5 date-safety tests must be extended, not weakened, in C1.
