# ADR 0007: Private taxi as a MOCK transport mode, priced per vehicle

Status: **Accepted by the project owner on 2026-11-02** (three decisions below).
Date: 2026-11-02
Related: PRD Q12 (price basis, amended here), A24; ADR 0006 (transport stays MOCK); ADR 0003 (demo booking).

## Context

The planning workflow had flights, trains and buses. `TransportMode.ROAD` existed in the domain but no provider returned it. The owner asked for private taxi options. A taxi is hired by the vehicle, so a per-traveller price (the answer to Q12 on 2026-10-30) would misstate its cost for any party larger than one.

## Decision

1. **Price basis: per vehicle.** A new `PriceBasis.PER_VEHICLE` is used for road quotes. Flights, trains and buses stay `PER_TRAVELLER`; hotels stay `PER_ROOM_NIGHT`. This amends the owner's Q12 answer for taxis only.
2. **Larger parties: the same vehicle type, enough to seat everyone.** Vehicles needed = ceil(travellers / seats). The cost line states the count ("N vehicle(s) at the quoted fare") and its quantity is that count.
3. **Demo booking simulation: taxis stay excluded.** The simulation covers flights, trains and buses only.

## Consequences

- **Domain:** `RoadDetails` (vehicle type, passenger capacity 1 to 60) joins the mode-specific details; a ROAD option without its capacity is rejected. `estimate_trip_cost` refuses a per-vehicle quote without a vehicle count.
- **Mock provider:** three fictional taxis (sedan 4 seats, SUV 6, van 12), labelled MOCK, with fictional operators. Money is integer minor units.
- **Persistence:** Alembic revision `0003` widens the `quotes.price_basis` CHECK constraint. Its downgrade refuses while any per-vehicle quote exists, because the older schema cannot hold it.
- **API:** `docs/openapi.json` changes additively (`PER_VEHICLE`, `RoadDetails`). Existing clients that handle only the older bases would not understand a taxi quote; this is a development-only API.
- **Frontend:** a "Private taxis" group, a per-vehicle note on every price, and a per-vehicle line in the demo estimate.
- **Unchanged:** booking stays disabled, approval stays human, budget is still deferred, and nothing is live.
