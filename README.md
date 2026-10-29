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
