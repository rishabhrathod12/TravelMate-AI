"""Provider interfaces and their implementations.

Interfaces and the typed errors they raise live here. Mock implementations live
in `app.providers.mock`. There is no live implementation yet: live providers need
the owner's authorisation (plan M13).

Callers (the research tools, M4) depend on `base`, `queries`, `errors` and
`retry`, never on a concrete provider. Concrete providers are chosen in one
place, `factory.build_providers`, called from the composition root in `main.py`
(ARCHITECTURE §3).
"""
