"""Architecture rules for the services and observability packages (ARCHITECTURE §3; plan M8).

- `observability/` is a leaf: it imports nothing else from the application, so logging can never
  pull in a service, a route or a secret.
- `services/` holds the access rules. It uses the domain, the workflow and the pure conversation
  draft, plus observability. It never reaches the API layer, the app factory, voice or settings.
  Only `booking.py` may use the (disabled) booking executor.
- Only the API routers and the composition root import `services/`.
- Neither package uses a network library.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
SERVICES_DIR = APP_DIR / "services"
OBSERVABILITY_DIR = APP_DIR / "observability"
NETWORK = {"httpx", "httpx2", "requests", "aiohttp", "urllib3", "socket", "openai"}
SERVICES_ALLOWED = (
    "app.domain",
    "app.conversation.draft",
    "app.observability",
    "app.services",
    "app.workflow",
    # Booking approvals (M10): the service asks the disabled executor, and re-checks a quote with
    # the same read-only research tools the workflow uses. Nothing wider.
    "app.booking.executor",
    "app.providers.queries",
    "app.tools.research",
)
SERVICES_FORBIDDEN = (
    "app.api",
    "app.main",
    "app.voice",
    "app.config",
    "app.persistence",
)


def imported_modules(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def app_modules(path: Path) -> list[str]:
    return [
        m
        for m in imported_modules(path.read_text(encoding="utf-8"))
        if m == "app" or m.startswith(("app.", "."))
    ]


def test_both_packages_exist_and_are_not_empty() -> None:
    assert {"trips.py", "ratelimit.py"} <= {p.name for p in python_files(SERVICES_DIR)}
    assert {"logs.py", "redaction.py", "request_id.py"} <= {
        p.name for p in python_files(OBSERVABILITY_DIR)
    }


@pytest.mark.parametrize("path", python_files(OBSERVABILITY_DIR), ids=lambda p: p.name)
def test_observability_imports_nothing_else_from_the_application(path: Path) -> None:
    others = [m for m in app_modules(path) if not under(m, "app.observability")]

    assert others == []


@pytest.mark.parametrize("path", python_files(SERVICES_DIR), ids=lambda p: p.name)
def test_services_use_only_what_they_are_allowed_to(path: Path) -> None:
    modules = app_modules(path)

    assert [m for m in modules if any(under(m, p) for p in SERVICES_FORBIDDEN)] == []
    assert [m for m in modules if not any(under(m, p) for p in SERVICES_ALLOWED)] == []


@pytest.mark.parametrize(
    "path", [*python_files(SERVICES_DIR), *python_files(OBSERVABILITY_DIR)], ids=lambda p: p.name
)
def test_neither_package_uses_a_network_library(path: Path) -> None:
    top = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}

    assert top & NETWORK == set()


def test_only_the_api_routers_and_the_composition_root_import_services() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if SERVICES_DIR not in path.parents
        and any(under(m, "app.services") for m in app_modules(path))
    )

    assert importers == [
        "api/booking.py",
        "api/planning.py",
        "api/problems.py",
        "main.py",
        "persistence/sql_booking_store.py",
        "persistence/sql_store.py",
    ]


def test_the_domain_and_the_workflow_do_not_depend_on_services_or_observability() -> None:
    offenders = [
        path.relative_to(APP_DIR).as_posix()
        for package in ("domain", "workflow", "llm", "providers", "tools", "conversation")
        for path in python_files(APP_DIR / package)
        if any(under(m, "app.services") for m in app_modules(path))
    ]

    assert offenders == []
