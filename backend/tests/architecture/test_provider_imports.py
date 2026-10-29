"""Architecture rules for the providers package (ARCHITECTURE §3, plan M3).

- Providers depend only on the domain (and the factory also on the settings).
- Interfaces never know the concrete mocks.
- Only the providers package itself may import the mocks, so callers depend on
  interfaces and the factory is the one place that chooses.
- Mock providers use no network library, so a mock can never make a real call.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
PROVIDERS_DIR = APP_DIR / "providers"
MOCK_DIR = PROVIDERS_DIR / "mock"
INTERFACE_MODULES = ("base.py", "queries.py", "errors.py", "retry.py")
NETWORK_LIBRARIES = {
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "urllib3",
    "http",
    "socket",
    "ssl",
    "ftplib",
    "smtplib",
    "websockets",
    "openai",
}


def imported_modules(source: str) -> list[str]:
    """Every module a file imports. A relative import that climbs out is shown with dots."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 1:
                found.append("." * node.level + (node.module or ""))
            elif node.level == 0:
                found.append(node.module or "")
    return found


def app_imports(source: str) -> list[str]:
    return [m for m in imported_modules(source) if m == "app" or m.startswith(("app.", "."))]


def under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_helper_reads_imports_correctly() -> None:
    source = (
        "import json\nfrom app.domain import base\nimport app.config\n"
        "from .. import x\nfrom . import y"
    )

    assert imported_modules(source) == ["json", "app.domain", "app.config", ".."]
    assert app_imports(source) == ["app.domain", "app.config", ".."]


def test_the_providers_package_is_present_and_not_empty() -> None:
    names = {p.relative_to(PROVIDERS_DIR).as_posix() for p in python_files(PROVIDERS_DIR)}

    assert {
        "base.py",
        "factory.py",
        "mock/transport.py",
        "mock/hotel.py",
        "mock/weather.py",
    } <= names


@pytest.mark.parametrize(
    "path", python_files(PROVIDERS_DIR), ids=lambda p: p.relative_to(APP_DIR).as_posix()
)
def test_providers_depend_only_on_the_domain_and_themselves(path: Path) -> None:
    allowed = ["app.domain", "app.providers"]
    if path.name == "factory.py":
        allowed.append("app.config")  # the one place that reads settings

    bad = [
        module
        for module in app_imports(path.read_text(encoding="utf-8"))
        if not any(under(module, prefix) for prefix in allowed)
    ]

    assert bad == []


@pytest.mark.parametrize("name", INTERFACE_MODULES)
def test_interfaces_do_not_know_the_concrete_providers(name: str) -> None:
    modules = app_imports((PROVIDERS_DIR / name).read_text(encoding="utf-8"))

    assert not any(
        under(m, "app.providers.mock") or under(m, "app.providers.factory") for m in modules
    )


@pytest.mark.parametrize("path", python_files(MOCK_DIR), ids=lambda p: p.name)
def test_mock_providers_use_no_network_library(path: Path) -> None:
    top_level = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}

    assert top_level & NETWORK_LIBRARIES == set()


def test_only_the_providers_package_imports_the_mocks() -> None:
    offenders = [
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if PROVIDERS_DIR not in path.parents
        and any(
            under(m, "app.providers.mock") for m in app_imports(path.read_text(encoding="utf-8"))
        )
    ]

    assert offenders == []


def test_the_domain_does_not_import_providers() -> None:
    offenders = [
        path.name
        for path in python_files(APP_DIR / "domain")
        if any(under(m, "app.providers") for m in app_imports(path.read_text(encoding="utf-8")))
    ]

    assert offenders == []
