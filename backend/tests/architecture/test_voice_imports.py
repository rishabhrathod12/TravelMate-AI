"""Architecture rules for voice (docs/VOICE_ASSISTANT_PLAN.md, ADR 0002, ADR 0003).

- The voice package depends only on the domain, the research tools, the settings and itself.
- It never imports booking, workflow internals, the LLM layer, mock providers or any network
  library, so voice cannot reach a provider, an LLM or a booking by import.
- Only the voice router and the application factory import it.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
VOICE_DIR = APP_DIR / "voice"
ALLOWED_PREFIXES = ("app.domain", "app.tools", "app.config", "app.voice")
FORBIDDEN_PREFIXES = (
    "app.booking",
    "app.workflow",
    "app.services",
    "app.llm",
    "app.providers",
    "app.persistence",
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
ALLOWED_IMPORTERS = {"api/voice.py", "main.py"}


def imported_modules(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            found.append(node.module or "")
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_voice_package_exists_and_is_not_empty() -> None:
    names = {p.name for p in python_files(VOICE_DIR)}

    assert {"__init__.py", "errors.py", "sessions.py", "tools.py"} <= names


@pytest.mark.parametrize("path", python_files(VOICE_DIR), ids=lambda p: p.name)
def test_voice_modules_import_only_what_they_are_allowed_to(path: Path) -> None:
    modules = imported_modules(path.read_text(encoding="utf-8"))
    app_modules = [m for m in modules if m == "app" or m.startswith(("app.", "."))]

    assert [m for m in app_modules if m.startswith(".")] == []  # absolute imports only
    assert [m for m in app_modules if not any(under(m, p) for p in ALLOWED_PREFIXES)] == []
    assert [m for m in app_modules if any(under(m, p) for p in FORBIDDEN_PREFIXES)] == []


@pytest.mark.parametrize("path", python_files(VOICE_DIR), ids=lambda p: p.name)
def test_voice_modules_use_no_network_library(path: Path) -> None:
    top_level = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}

    assert top_level & NETWORK_LIBRARIES == set()


def test_only_the_voice_router_and_the_app_factory_import_voice() -> None:
    offenders = [
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if VOICE_DIR not in path.parents
        and any(under(m, "app.voice") for m in imported_modules(path.read_text(encoding="utf-8")))
        and path.relative_to(APP_DIR).as_posix() not in ALLOWED_IMPORTERS
    ]

    assert offenders == []


def test_no_booking_workflow_or_llm_module_imports_voice() -> None:
    for name in ("booking", "workflow", "llm", "providers", "domain"):
        directory = APP_DIR / name
        if not directory.exists():
            continue
        for path in python_files(directory):
            modules = imported_modules(path.read_text(encoding="utf-8"))
            assert not any(under(m, "app.voice") for m in modules), path


def test_the_voice_package_never_mentions_booking_in_code() -> None:
    for path in python_files(VOICE_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not any("booking" in name for name in names), path
