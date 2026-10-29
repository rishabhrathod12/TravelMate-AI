"""Write the mock transport fixtures for the frontend demo.

Run from the repository root with the backend environment:

    backend/.venv/Scripts/python.exe backend/scripts/export_demo_fixtures.py

It only writes `frontend/src/demo/transportFixtures.json`. A backend test checks that the file
matches, so forgetting to run this fails the test run instead of letting the copies drift.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.providers.mock.export import EXPORT_RELATIVE_PATH, export_transport_fixtures  # noqa: E402


def main() -> None:
    target = BACKEND_DIR.parent / EXPORT_RELATIVE_PATH
    target.write_text(export_transport_fixtures(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
