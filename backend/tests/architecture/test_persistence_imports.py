"""Architecture rules for the persistence package (ARCHITECTURE §3; plan M9).

- Only `persistence/` imports SQLAlchemy, Alembic or the database driver. (The migrations folder
  sits outside `app/` and is the one other place that uses Alembic.)
- It implements the store interface and uses the project's data types, and nothing else from the
  application: not the API, the app factory, voice, settings or booking.
- Only the composition root imports it. Services and the workflow never reach the database
  directly; they use the `TripStore` interface.
- No SQL is built from strings: the ORM does the writing, so values are always bound parameters.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
PERSISTENCE_DIR = APP_DIR / "persistence"
DATABASE_LIBRARIES = {"sqlalchemy", "alembic", "psycopg", "psycopg2", "psycopg_binary"}
ALLOWED = (
    "app.domain",
    "app.services.store",
    "app.conversation.draft",
    "app.workflow.state",
    "app.persistence",
)
FORBIDDEN = ("app.api", "app.main", "app.voice", "app.config", "app.booking", "app.llm")


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


def test_the_package_exists_and_is_not_empty() -> None:
    names = {p.name for p in python_files(PERSISTENCE_DIR)}

    assert {"models.py", "engine.py", "sql_store.py", "policy.py"} <= names


@pytest.mark.parametrize("path", python_files(PERSISTENCE_DIR), ids=lambda p: p.name)
def test_persistence_uses_only_what_it_is_allowed_to(path: Path) -> None:
    modules = app_modules(path)

    assert [m for m in modules if any(under(m, p) for p in FORBIDDEN)] == []
    assert [m for m in modules if not any(under(m, p) for p in ALLOWED)] == []


def test_only_the_persistence_package_imports_a_database_library() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if PERSISTENCE_DIR not in path.parents
        and DATABASE_LIBRARIES
        & {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}
    )

    assert importers == []


def test_only_the_composition_root_imports_persistence() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if PERSISTENCE_DIR not in path.parents
        and any(under(m, "app.persistence") for m in app_modules(path))
    )

    assert importers == ["main.py"]


@pytest.mark.parametrize("package", ["domain", "workflow", "services", "api", "llm", "tools"])
def test_nothing_else_depends_on_the_database_layer(package: str) -> None:
    offenders = [
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR / package)
        if any(under(m, "app.persistence") for m in app_modules(path))
    ]

    assert offenders == []


@pytest.mark.parametrize("path", python_files(PERSISTENCE_DIR), ids=lambda p: p.name)
def test_no_sql_is_built_from_strings(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    called_text = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "text"
    ]

    assert "text" not in names or called_text == []
    assert "exec_driver_sql" not in attributes


@pytest.mark.parametrize("path", python_files(PERSISTENCE_DIR), ids=lambda p: p.name)
def test_the_database_url_is_never_logged_or_printed(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]

    assert "print" not in calls
