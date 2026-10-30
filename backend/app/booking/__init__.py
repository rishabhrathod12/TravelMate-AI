"""Booking execution, which is switched off (ARCHITECTURE §6, SECURITY §4; plan M10).

Real booking is Milestone 14 and needs the owner's written authorization, a reviewed executor and a
provider decision. Until then this package holds only:
- the shape of a booking attempt and of the provider-facing client (an interface only);
- `DisabledBookingExecutor`, which refuses every attempt and holds no client at all;
- a factory that refuses to build anything else.

Only the services layer (and the composition root that wires it) may import this package. The
planning workflow, the model layer, the tools, the conversation and voice code must never reach it,
so no model, tool or spoken request can book anything. Architecture tests enforce that.
"""
