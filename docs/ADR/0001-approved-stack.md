# ADR 0001: Approved technology stack

Status: Accepted (by project owner, Milestone 0 approval)
Date: 2026-10-29

## Context

TravelMate AI needs a backend for a multi-step planning workflow with human pauses, typed data from several providers, an LLM, durable storage, and a browser UI. The owner approved the stack below as defaults for Milestone 0. Choices are recorded here so later changes are deliberate.

## Decision

| Area | Choice | Notes |
|---|---|---|
| Language (backend) | Python 3.12 | Pinned in `backend/pyproject.toml`. The existing local venv (Python 3.14.5) is not the target and is replaced in M1. |
| Web framework | FastAPI | REST API with OpenAPI generation. |
| Validation | Pydantic (v2) | Request, response, tool and LLM output schemas. |
| Agent orchestration | LangGraph | Planning graph, interrupts for human input, checkpointing. |
| LLM | OpenAI API behind a project `LLMClient` interface | No code outside `app/llm/` imports the OpenAI SDK. |
| Database | PostgreSQL | Durable storage and LangGraph checkpoints. |
| ORM / data access | SQLAlchemy 2.x | Typed models and repositories. |
| Migrations | Alembic | Reviewed revisions. |
| Frontend | React, TypeScript, Vite | Single-page planning UI. |
| Backend tests | Pytest | Unit, contract, integration, API and architecture tests. |
| Frontend tests | Vitest (unit), Playwright (end to end) | Added in M1 and M11. Vitest and Playwright are not part of the approved list in the owner's message; this ADR records them as the proposed defaults for the frontend test layer. |
| Local environment | Docker Compose | PostgreSQL first, app services later. |
| Queue / cache | Redis and Celery | **Not adopted.** Introduced only when a background-job requirement justifies them, through a new ADR. |

## Consequences

- Provider data flows through interfaces so that mock and live adapters are interchangeable.
- LangGraph is a dependency of the workflow layer only. Domain code does not depend on it.
- The LLM provider is replaceable; switching to another provider requires a new adapter, not a rewrite of the workflow.
- Background work (for example, scheduled price checks) is not designed yet. Adding it will need its own ADR.

## Alternatives considered

- Redis and Celery from the start: rejected for the MVP because no requirement needs background retries that outlive a request.
- Direct SDK calls without an LLM interface: rejected because it would make tests depend on the network and make provider changes costly.

## Open items

- The exact versions of each library are chosen and pinned in M1.
- The Vitest and Playwright choice should be confirmed by the owner in review.
