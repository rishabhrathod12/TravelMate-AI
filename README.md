# TravelMate AI

An AI travel planner, built as a portfolio project to learn agentic AI engineering. You describe a trip by typing or (in development) by a mock voice session; it researches transport, hotels and weather, compares options, estimates the cost, drafts an itinerary, and walks you through a human approval step. **Nothing is ever booked or paid.**

## Status: complete at its current scope

The project owner declared it complete at its current scope on 2026-11-02 (`docs/PRD.md` A23). What that means:

- **Built and tested:** the planning workflow, the planning and booking-intent APIs, PostgreSQL persistence, the approval path (with booking switched off), and the web interface (dark home with a voice button and a message box, a conversation view, the trip form and the demo comparison).
- **All provider data is MOCK.** Transport, hotels and weather come from labelled fixtures for Indore and Goa. No live provider is connected (`docs/ADR/0006-transport-and-hotels-stay-mock.md`). A live weather adapter was decided on but never built (`docs/ADR/0005-live-weather-open-meteo.md`).
- **No real language model, voice service, login or payment.** The chat and the itinerary use labelled stand-ins, and voice is a labelled mock. Real booking does not exist and `BOOKING_ENABLED=false` is enforced at startup.
- **Development only:** the planning API, chat and voice refuse to start in production (no real authentication exists). A production build of the interface shows them switched off; the trip form and demo comparison still work from the menu.

Read next: `docs/ACCEPTANCE.md` (what was verified and what was not, plus the known limitations), `docs/IMPLEMENTATION_PLAN.md` (milestone status), `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`. Working rules for contributors, human or AI, are in `CLAUDE.md`.

## Backend setup (Python 3.12)

Requires Python 3.12. The project uses `pip` with `backend/pyproject.toml` as the only dependency declaration.

```bash
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
```

Run the tests, lint and type checks:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m ruff format --check backend
cd backend && .venv/Scripts/python.exe -m mypy
```

Tests need no network and no API keys. The PostgreSQL tests are skipped unless `TEST_DATABASE_URL` is set (see below); CI runs them.

Start the API locally (health endpoint only):

```bash
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Then open `http://127.0.0.1:8000/health`. The health endpoint needs no API keys.

Configuration is read from environment variables (see `.env.example`). Never commit `.env`.

### Running the whole demo locally

The planning API and the chat are off by default and every limit must be set explicitly (there are no hidden defaults). These non-secret values switch them on for local development:

```bash
API_ENABLED=true API_DEV_PRINCIPAL=dev API_CURRENCY=INR \
API_RUN_MAX_STEPS=50 API_RUN_MAX_TOOL_CALLS=30 API_RUN_MAX_HUMAN_ROUNDS=5 \
API_MAX_RUNS_PER_HOUR_PER_OWNER=50 \
CONVERSATION_ENABLED=true CONVERSATION_MAX_MESSAGE_CHARS=500 \
CONVERSATION_LLM_MAX_OUTPUT_TOKENS=300 CONVERSATION_LLM_TIMEOUT_SECONDS=10 \
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000
```

No key is needed and nothing leaves your machine: the chat and itinerary use scripted stand-ins, and all travel data is mock. Without `DATABASE_URL`, trips and runs live in memory and are lost on restart.

## Frontend setup (Node 22 or newer)

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173 (use localhost, not 127.0.0.1)
npm run lint
npm run typecheck
npm test
npm run build
```

In development, Vite forwards `/health` and `/api` to the backend on `127.0.0.1:8000`, so the browser needs no CORS. With the backend running as above you can try:

- **Chat:** type "plan my 5 days itinerary for Goa this weekend", or "from Indore to Goa on 12 December, one way, 1 person" then "Use these details".
- **Server planning panel:** under the demo results, enter the number of rooms, plan, choose options, edit the itinerary and walk through the approval step.
- **Voice:** the mic button starts a labelled MOCK voice session (no microphone, no sound, scripted replies).
- **Trip form:** the menu entry "Trip Form" works without the backend.

What is real and what is not:

- **Real:** the backend, its API and database layer, and the approval logic. The status line at the bottom of the page calls `GET /health`.
- **Mock:** every transport option, hotel, weather value, price and quote. They are labelled MOCK with fictional names, and no AI model wrote them.
- **Nothing is booked.** Approving records your agreement to exact terms for 15 minutes and nothing else; the booking button is shown disabled and `execute` always answers `409 booking_disabled`.

To point the interface at a backend on another address, set `VITE_API_BASE_URL` in a local `frontend/.env.local` file (git-ignored). That value is visible in the browser, so it must never hold a secret. The backend has no CORS policy, so a different origin is blocked unless you use the Vite proxy.

## Local database

PostgreSQL runs from Docker Compose. Choose a local password and export it (or put it in an uncommitted `.env`):

```bash
export POSTGRES_PASSWORD=<your-local-password>
docker compose up -d db
docker compose ps
```

The database listens on `127.0.0.1:5432` only. To use it from the application:

```bash
# Your own shell only. The URL holds a password, so it never goes in a committed file.
export DATABASE_URL='postgresql+psycopg://postgres:<your-local-password>@127.0.0.1:5432/travelmate'

# Create the tables and the application's database role (run as the database owner).
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
# Print the SQL instead of running it (needs no database):  ... upgrade head --sql
# Undo it:                                                   ... downgrade base
```

With `DATABASE_URL` set, the planning API keeps trips, runs, booking intents and audit events in PostgreSQL and a restart no longer loses them. Without it, records stay in memory. `DATABASE_URL` is required when `APP_ENV=production`. Run checkpoints are still in memory, so a run that was in progress when the server stopped is marked failed on the next start.

The tests that need a real server run in CI against a PostgreSQL service. To run them here, point `TEST_DATABASE_URL` at an empty database that you do not mind losing (they create and drop its tables) and run `pytest -m integration`.

## Continuous integration

`.github/workflows/ci.yml` runs backend lint, type check and tests, a PostgreSQL job, frontend lint, type check, tests (including automated accessibility checks) and build, a dependency audit (`pip-audit`, `npm audit`) and a secret scan (gitleaks). It uses no repository secrets, and its GitHub Actions are pinned to commit SHAs.
