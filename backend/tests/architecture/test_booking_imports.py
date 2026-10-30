"""Who may approve, and who may reach booking (ARCHITECTURE §3, §6; SECURITY §5; plan M10).

An approval is a person's decision, so no model, tool, workflow step, voice session, provider or
conversation code may create one or even import the services that do. Only `services/booking.py`
builds an approval, and only the services and the composition root touch `app.booking`.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
# Packages that act for a model or a provider and so must never be able to approve anything.
AGENT_SIDE = ("workflow", "llm", "tools", "conversation", "voice", "providers", "domain")
APPROVAL_TYPES = {"ApprovalRecord", "Approval"}


def python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def imported_modules(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(node.module or "")
    return found


def under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def constructed_names(path: Path) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


@pytest.mark.parametrize(
    "path",
    [p for package in AGENT_SIDE for p in python_files(APP_DIR / package)],
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_agent_side_code_cannot_reach_booking_or_approvals(path: Path) -> None:
    modules = imported_modules(path)

    forbidden = ("app.booking", "app.services.booking", "app.services.booking_store")
    assert [m for m in modules if any(under(m, f) for f in forbidden)] == []


def test_only_the_booking_service_builds_an_approval() -> None:
    builders = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if constructed_names(path) & APPROVAL_TYPES
    )

    # The SQL store builds the approval *row* it was handed (a different type) and reads rows back
    # into records; neither is a decision. The decision is only ever made in the service.
    assert builders == ["persistence/sql_booking_store.py", "services/booking.py"]


def test_the_sql_store_builds_approvals_only_from_a_record_it_was_given() -> None:
    source = (APP_DIR / "persistence" / "sql_booking_store.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions_building_records = {
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ApprovalRecord"
    }

    # Reading an approval back is the only place it builds a record; recording takes one as input.
    assert functions_building_records == {"latest_approval"}


def test_only_services_and_the_composition_root_import_the_booking_package() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if (APP_DIR / "booking") not in path.parents
        and any(under(m, "app.booking") for m in imported_modules(path))
    )

    assert importers == ["main.py", "services/booking.py"]


def test_the_booking_package_imports_nothing_that_can_reach_a_provider() -> None:
    network = {"httpx", "requests", "aiohttp", "urllib3", "socket", "openai", "stripe"}
    for path in python_files(APP_DIR / "booking"):
        top = {m.split(".")[0] for m in imported_modules(path)}
        assert top & network == set(), path.name
        assert not [m for m in imported_modules(path) if under(m, "app.providers")], path.name
