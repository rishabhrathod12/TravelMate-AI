"""Mock providers: deterministic fixtures, labelled MOCK, no network.

They exist so the system can run end to end with no network and no keys (plan
M3). Everything they return is sample data. It must never be shown as a real
price, schedule, availability or forecast (PRD §9, CLAUDE.md).
"""
