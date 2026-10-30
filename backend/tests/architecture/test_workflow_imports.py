"""Architecture rules for the workflow package (ARCHITECTURE §3, §4; plan M7).

- `workflow/` must never import `booking/` (CLAUDE.md), and no code in it may name booking,
  approval or payment: the workflow has no way to reach them.
- It depends on the domain, the tool/provider/LLM interfaces and the conversation draft, and on
  nothing that does I/O of its own: no API, voice, persistence or network library.
- It is the only package that imports LangGraph or LangChain.
- Nothing below it depends on it.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
WORKFLOW_DIR = APP_DIR / "workflow"
ALLOWED_PREFIXES = (
    "app.domain",
    "app.tools",
    "app.providers",
    "app.llm",
    "app.conversation.draft",
    "app.workflow",
)
FORBIDDEN_PREFIXES = (
    "app.booking",
    "app.api",
    "app.voice",
    "app.persistence",
    "app.services",
    "app.config",
    "app.main",
)
NETWORK_LIBRARIES = {"httpx", "httpx2", "requests", "aiohttp", "urllib3", "socket", "openai"}
FRAMEWORKS = {"langgraph", "langchain", "langchain_core", "langsmith"}
BOOKING_WORDS = ("book", "approval", "approve", "payment", "pay")


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


def test_the_package_exists_and_is_not_empty() -> None:
    names = {p.name for p in python_files(WORKFLOW_DIR)}

    assert {"graph.py", "runner.py", "state.py", "serde.py", "limits.py", "tracing.py"} <= names


@pytest.mark.parametrize("path", python_files(WORKFLOW_DIR), ids=lambda p: p.name)
def test_workflow_modules_import_only_what_they_are_allowed_to(path: Path) -> None:
    modules = imported_modules(path.read_text(encoding="utf-8"))
    app_modules = [m for m in modules if m == "app" or m.startswith(("app.", "."))]

    assert [m for m in app_modules if m.startswith(".")] == []
    assert [m for m in app_modules if any(under(m, p) for p in FORBIDDEN_PREFIXES)] == []
    assert [m for m in app_modules if not any(under(m, p) for p in ALLOWED_PREFIXES)] == []


def test_workflow_never_imports_booking() -> None:
    reachable = {
        m for path in python_files(WORKFLOW_DIR) for m in imported_modules(path.read_text("utf-8"))
    }

    assert not [m for m in reachable if "booking" in m]


@pytest.mark.parametrize("path", python_files(WORKFLOW_DIR), ids=lambda p: p.name)
def test_workflow_uses_no_network_library(path: Path) -> None:
    top_level = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}

    assert top_level & NETWORK_LIBRARIES == set()


@pytest.mark.parametrize("path", python_files(WORKFLOW_DIR), ids=lambda p: p.name)
def test_no_code_in_the_workflow_names_booking_approval_or_payment(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.name.lower() for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    names |= {n.name.lower() for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}

    offenders = {name for name in names if any(word in name for word in BOOKING_WORDS)}
    assert offenders == set()


def test_only_the_workflow_package_imports_langgraph_or_langchain() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if WORKFLOW_DIR not in path.parents
        and FRAMEWORKS & {m.split(".")[0] for m in imported_modules(path.read_text("utf-8"))}
    )

    assert importers == []


# The composition root builds it, the service runs it, and the API describes its inputs and
# outputs. Nothing else may reach it.
WORKFLOW_USERS = [
    "api/planning.py",
    "main.py",
    "persistence/sql_store.py",
    "services/booking.py",
    "services/quote_source.py",
    "services/store.py",
    "services/trips.py",
]


def test_only_the_composition_root_the_service_and_the_api_schemas_import_it() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if WORKFLOW_DIR not in path.parents
        and any(under(m, "app.workflow") for m in imported_modules(path.read_text("utf-8")))
    )

    assert importers == WORKFLOW_USERS


@pytest.mark.parametrize("package", ["domain", "providers", "tools", "llm"])
def test_nothing_below_the_workflow_depends_on_it(package: str) -> None:
    offenders = [
        path.name
        for path in python_files(APP_DIR / package)
        if any(under(m, "app.workflow") for m in imported_modules(path.read_text("utf-8")))
    ]

    assert offenders == []
