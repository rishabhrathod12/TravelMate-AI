# ADR 0003 — Simulated demo booking is separate from real booking

Status: **ACCEPTED on 2026-10-30** by the project owner (approval of decisions A to J with the
recommendations in the audit of that date).

## Context

The product compares flights, trains and buses, but only mock providers exist: no live transport
API is authorised (PRD Q1), `BOOKING_ENABLED` must stay false, and booking execution is not
implemented (M14). The owner wants users to be able to walk through a booking-like flow for
demonstration. `ARCHITECTURE.md` §6 and `SECURITY.md` §4 say a booking is never reported as
`CONFIRMED` unless a provider confirmation was received and validated, and `CLAUDE.md` forbids
claiming a booking succeeded without one.

## Decision

1. A **demo booking** is a different thing from a real booking. It has its own type
   (`DemoBooking`, `kind: "DEMO_SIMULATION"`, `is_real: false`) and its own code
   (`frontend/src/demoBooking/`). It does **not** use `BookingIntent`, `Approval`, `BookingStatus`
   (in particular never `CONFIRMED`), the `booking/` package, or the `BOOKING_ENABLED` setting.
2. It performs no I/O: no network request, no provider call, no storage and no payment. It is
   pure in-memory code. A reload discards every demo booking.
3. Its result is labelled **"DEMO — NOT A REAL BOOKING"**. Its reference is a per-session counter
   in the form `DEMO-BOOKING-001`. It is explicitly not a PNR, a ticket number or a provider
   confirmation and is not unique across sessions.
4. Only an option that is shown as AVAILABLE, has a price and has a matching quote can be
   simulated. UNKNOWN and UNAVAILABLE options cannot. The simulation never guesses.
5. Submitting the same selection again returns the first result and creates nothing new.
6. The user must tick an explicit acknowledgement before the "Simulate booking" button works.
   No control in the demo flow says approve, book now or pay.
7. It applies to the outbound leg only, because return-leg options are not modelled (PRD Q13).
8. The simulation is not exposed to the voice assistant or to any LLM tool. A spoken request
   cannot trigger it, and nothing an LLM writes can create one.
9. Prices shown are "as quoted". PRD Q12 has since been answered (2026-10-30): a transport fare is
   per traveller. The demo booking still shows one traveller's quoted price plus sample fees, labelled
   as such, and not the trip estimate.
10. Real booking, payment, cancellation and live providers stay disabled and need their own
    authorisation (M13, M14). The open lifecycle questions (PRD Q7 to Q11, Q15) are untouched.

## Consequences

- Tests enforce the separation: the demo module is scanned for network, storage, voice, booking
  and approval references, and a runtime test checks that `fetch` is never called.
- A future backend demo service would need its own ADR; it must keep these rules.
- If a real booking flow is ever built, it will be a separate path. The demo flow must not be
  turned into it by renaming, and a demo reference must never be stored as a booking reference.

## Alternatives considered

- Reusing `BookingIntent` with a "demo" flag: rejected, because one wrong branch would make a
  fake result look real.
- A backend demo-booking service: deferred until the API layer (M8) exists.
- Persisting demo bookings: rejected for now (M9 is not built).
