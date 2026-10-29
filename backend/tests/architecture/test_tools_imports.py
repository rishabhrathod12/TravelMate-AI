"""Architecture rules for the research tools (ARCHITECTURE §3, §4).

- Tools depend on the domain and on provider *interfaces* only, never on a concrete
  provider, the factory or the settings.
- Nothing in tools can reach booking, the API, the workflow or an LLM.
- Tools make no network call of their own.
- The domain and providers never depend on tools.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
TOOLS_DIR = APP_DIR / "tools"
ALLOWED_PROVIDER_MODULES = (
    "app.providers.base",
    "app.providers.queries",
    "app.providers.errors",
    "app.providers.retry",
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
    "openai",
}


def imported_modules(source: str) -> list[str]:
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


def allowed(module: str) -> bool:
    return (
        under(module, "app.domain")
        or under(module, "app.tools")
        or module in ALLOWED_PROVIDER_MODULES
    )


def test_the_tools_package_is_present_and_not_empty() -> None:
    names = {p.name for p in python_files(TOOLS_DIR)}

    assert {"research.py", "comparison.py", "recorder.py", "results.py", "errors.py"} <= names


@pytest.mark.parametrize("path", python_files(TOOLS_DIR), ids=lambda p: p.name)
def test_tools_depend_only_on_the_domain_and_provider_interfaces(path: Path) -> None:
    bad = [m for m in app_imports(path.read_text(encoding="utf-8")) if not allowed(m)]

    assert bad == []


@pytest.mark.parametrize("path", python_files(TOOLS_DIR), ids=lambda p: p.name)
def test_tools_never_import_a_concrete_provider_the_factory_or_the_settings(path: Path) -> None:
    modules = app_imports(path.read_text(encoding="utf-8"))
    forbidden = ("app.providers.mock", "app.providers.factory", "app.config", "app.main")

    assert not [m for m in modules if any(under(m, prefix) for prefix in forbidden)]


@pytest.mark.parametrize("path", python_files(TOOLS_DIR), ids=lambda p: p.name)
def test_tools_make_no_network_call_of_their_own(path: Path) -> None:
    top_level = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}

    assert top_level & NETWORK_LIBRARIES == set()


def test_no_tool_can_reach_booking_the_api_the_workflow_or_an_llm() -> None:
    reachable = {
        m for path in python_files(TOOLS_DIR) for m in app_imports(path.read_text(encoding="utf-8"))
    }
    blocked = (
        "app.booking",
        "app.api",
        "app.workflow",
        "app.llm",
        "app.persistence",
        "app.services",
    )

    assert not [m for m in reachable if any(under(m, prefix) for prefix in blocked)]


@pytest.mark.parametrize("package", ["domain", "providers"])
def test_the_domain_and_providers_never_depend_on_tools(package: str) -> None:
    offenders = [
        path.name
        for path in python_files(APP_DIR / package)
        if any(under(m, "app.tools") for m in app_imports(path.read_text(encoding="utf-8")))
    ]

    assert offenders == []
