# TravelMate-AI
Travel Mate AI is a AI travel planner 

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

Start the API locally:

```bash
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Then open `http://127.0.0.1:8000/health`. The health endpoint needs no API keys.

Configuration is read from environment variables (see `.env.example`). Never commit `.env`.

## Frontend setup (Node 22 or newer)

```bash
cd frontend
npm ci
npm run dev        # the prototype, at http://localhost:5173
npm run lint
npm run typecheck
npm test
npm run build
```

### Frontend prototype (demo data)

The interface is a prototype built before the backend has trip, option or approval endpoints. To view it:

```bash
# Terminal 1 (optional): the real backend, for the status line at the top of the page
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload

# Terminal 2
cd frontend
npm run dev
```

Open `http://localhost:5173` (use `localhost`, not `127.0.0.1`). The page works without the backend and then shows "Backend: not reachable".

What is real and what is not:

- **Real:** the backend status line, which calls `GET /health` (the only endpoint that exists). In development Vite forwards `/health` to `127.0.0.1:8000`, so the browser needs no CORS.
- **Demo:** everything shown after "Preview with demo data" (transport and hotel options, quotes, the cost estimate, the itinerary and the approval preview). It is hand-written sample data in `frontend/src/demo/demoData.ts`, labelled MOCK, with fictional names and round amounts. It is not real prices, availability or schedules, and no AI model wrote it.
- **Nothing is booked.** The approval preview is read-only, its "Approve" button is disabled, and real booking is disabled in the project.
- **Not stored:** the prototype saves nothing; a refresh clears it.

To point the interface at a backend on another address, set `VITE_API_BASE_URL` in a local `frontend/.env.local` file (git-ignored). That value is visible in the browser, so it must never hold a secret, and the backend has no CORS policy yet, so a different origin will be blocked until Milestone 8.

## Local database

PostgreSQL runs from Docker Compose. Choose a local password and export it (or put it in an uncommitted `.env`):

```bash
export POSTGRES_PASSWORD=<your-local-password>
docker compose up -d db
docker compose ps
```

The database listens on `127.0.0.1:5432` only. To use it from the application (Milestone 9):

```bash
# Your own shell only. The URL holds a password, so it never goes in a committed file.
export DATABASE_URL='postgresql+psycopg://postgres:<your-local-password>@127.0.0.1:5432/travelmate'

# Create the tables and the application's database role (run as the database owner).
aitravel/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
# Print the SQL instead of running it (needs no database):  ... upgrade head --sql
# Undo it:                                                   ... downgrade base
```

With `DATABASE_URL` set, the planning API keeps trips, runs and audit events in PostgreSQL and a restart no longer loses them. Without it, records stay in memory as before. `DATABASE_URL` is required when `APP_ENV=production`. Run checkpoints are still in memory, so a run that was in progress when the server stopped is marked failed on the next start.

The tests that need a real server run in CI against a PostgreSQL service. To run them here, point `TEST_DATABASE_URL` at an empty database that you do not mind losing (they create and drop its tables) and run `pytest -m integration`.

## Continuous integration

`.github/workflows/ci.yml` runs backend lint, type check and tests, frontend lint, type check, tests and build, a dependency audit (`pip-audit`, `npm audit`) and a secret scan (gitleaks). It uses no repository secrets.
