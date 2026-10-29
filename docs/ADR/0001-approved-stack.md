# ADR 0001: Approved technology stack

Status: Accepted (by project owner, Milestone 0 approval)
Date: 2026-10-29

## Context

TravelMate AI needs a backend for a multi-step planning workflow with human pauses, typed data from several providers, an LLM, durable storage, and a browser UI. The owner approved the stack below as defaults for Milestone 0. Choices are recorded here so later changes are deliberate.

## Decision

| Area | Choice | Notes |
|---|---|---|
| Language (backend) | Python 3.12 | Pinned in `backend/pyproject.toml`. The existing local venv `aitravel/` (Python 3.14.5) is not the target. It is left unchanged and unused; backend work uses `backend/.venv`. |
| Web framework | FastAPI | REST API with OpenAPI generation. |
| Validation | Pydantic (v2) | Request, response, tool and LLM output schemas. |
| Agent orchestration | LangGraph | Planning graph, interrupts for human input, checkpointing. |
| LLM | OpenAI API behind a project `LLMClient` interface | No code outside `app/llm/` imports the OpenAI SDK. |
| Database | PostgreSQL | Durable storage and LangGraph checkpoints. |
| ORM / data access | SQLAlchemy 2.x | Typed models and repositories. |
| Migrations | Alembic | Reviewed revisions. |
| Frontend | React, TypeScript, Vite | Single-page planning UI. |
| Backend tests | Pytest | Unit, contract, integration, API and architecture tests. |
| Frontend tests | Vitest (unit), Playwright (end to end) | Vitest is set up in M1. Playwright is added in M11 and is not installed yet. The owner approved both after the M1 review. |
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

## M1 tool and version choices

- Frontend packages are pinned exactly in `frontend/package.json` and `frontend/package-lock.json`. Versions were chosen at least two weeks after release: React 19.2, Vite 8.3, TypeScript 6.0, Vitest 5.0, ESLint 10, Testing Library, jsdom.
- Backend libraries use compatible-range pins in `backend/pyproject.toml`. `pytest` is `>=9.0.3,<10`. `pip-audit` reports PYSEC-2026-1845 (aliases CVE-2025-71176, GHSA-6w46-j5rx-g56g) against pytest 8.4.2: through 9.0.2 on UNIX, pytest relies on `/tmp/pytest-of-{user}` directories, which can allow a local denial of service or privilege gain. The reported fix version is 9.0.3. The risk applies to the Linux CI runner more than to a Windows developer machine, and a failing audit step would block CI. Installed pytest 9.2.0 audits clean, `pip check` reports no conflicts, and the tests, Ruff and strict mypy pass.
- Local PostgreSQL: `postgres:17-alpine` image, bound to localhost.
- Dependency audit: `pip-audit` (backend) and `npm audit --audit-level=high` (frontend).
- Secret scanning: `gitleaks` through `gitleaks/gitleaks-action@v2`. The action's free licence covers personal accounts; revisit if the repository moves to an organisation.
- CI actions are pinned to major version tags. Pinning them to full commit SHAs is a planned CI hardening task in M12 (see `docs/IMPLEMENTATION_PLAN.md`).

## Open items

- PostgreSQL start from Docker Compose is deferred and unverified. Docker is not available on the development machine. Verify it when Docker is available and the database is first needed (M9).
- GitHub Actions commit-SHA pinning: M12.
