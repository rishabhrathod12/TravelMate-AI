"""Architecture rules for the conversation package (docs/VOICE_ASSISTANT_PLAN.md, V5).

It may use the domain, the LLM layer (the interface, never a vendor) and itself. It reaches no
booking, workflow, providers, voice transport, persistence or network library, so a conversation
can never trigger a booking or a provider call by import. Nothing else imports it yet.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
CONVERSATION_DIR = APP_DIR / "conversation"
ALLOWED_PREFIXES = ("app.domain", "app.llm", "app.conversation")
FORBIDDEN_PREFIXES = (
    "app.booking",
    "app.workflow",
    "app.services",
    "app.providers",
    "app.persistence",
    "app.voice",
    "app.api",
    "app.tools",
)
NETWORK_LIBRARIES = {
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "urllib3",
    "http",
    "socket",
    "ssl",
    "websockets",
    "openai",
    "smtplib",
    "ftplib",
}


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
    names = {p.name for p in python_files(CONVERSATION_DIR)}

    assert {"__init__.py", "dates.py", "claims.py", "draft.py", "manager.py"} <= names


@pytest.mark.parametrize("path", python_files(CONVERSATION_DIR), ids=lambda p: p.name)
def test_conversation_modules_import_only_what_they_are_allowed_to(path: Path) -> None:
    modules = imported_modules(path.read_text(encoding="utf-8"))
    app_modules = [m for m in modules if m == "app" or m.startswith(("app.", "."))]

    assert [m for m in app_modules if m.startswith(".")] == []
    assert [m for m in app_modules if not any(under(m, p) for p in ALLOWED_PREFIXES)] == []
    assert [m for m in app_modules if any(under(m, p) for p in FORBIDDEN_PREFIXES)] == []


@pytest.mark.parametrize("path", python_files(CONVERSATION_DIR), ids=lambda p: p.name)
def test_conversation_modules_use_no_network_library(path: Path) -> None:
    top_level = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}

    assert top_level & NETWORK_LIBRARIES == set()


def test_only_the_conversation_package_imports_it() -> None:
    offenders = [
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if CONVERSATION_DIR not in path.parents
        and any(
            under(m, "app.conversation") for m in imported_modules(path.read_text(encoding="utf-8"))
        )
    ]

    assert offenders == []


def test_the_conversation_package_never_mentions_booking_in_code() -> None:
    for path in python_files(CONVERSATION_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not any("booking" in name for name in names), path
