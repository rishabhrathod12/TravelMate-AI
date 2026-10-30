"""Write the OpenAPI document of the whole API to `docs/openapi.json`.

Run from the repository root with the backend environment:

    aitravel/Scripts/python.exe backend/scripts/export_openapi.py

A backend test checks that the committed file matches a fresh build, so an API change that is not
regenerated and reviewed fails the test run instead of drifting.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.openapi_export import OPENAPI_RELATIVE_PATH, build_openapi_document  # noqa: E402


def main() -> None:
    target = BACKEND_DIR.parent / OPENAPI_RELATIVE_PATH
    target.write_text(build_openapi_document(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
