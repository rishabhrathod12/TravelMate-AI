"""Architecture rules for the LLM package (SECURITY §3, ARCHITECTURE §2, PRD AC-07).

- It depends only on the domain and itself, so it can reach neither booking code, the
  providers, the tools, the settings nor the API.
- It imports no network library, and no vendor SDK except the OpenAI SDK in exactly one module,
  `openai_transport.py` (ADR 0001, approved 2026-10-30). Everything else takes a transport or a
  client that is passed in, so only that one file can reach the network.
- The rest of the application never reaches into it except through its modules, and
  the domain, providers and tools never depend on it.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
LLM_DIR = APP_DIR / "llm"
OPENAI_TRANSPORT = "openai_transport.py"
SDKS_AND_NETWORK = {
    "openai",
    "anthropic",
    "langchain",
    "langgraph",
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "urllib3",
    "http",
    "socket",
    "ssl",
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


def test_the_llm_package_is_present_and_not_empty() -> None:
    names = {p.name for p in python_files(LLM_DIR)}

    assert {
        "base.py",
        "budget.py",
        "drafter.py",
        "fake.py",
        "openai_client.py",
        "openai_transport.py",
        "plan_writer.py",
        "scripted.py",
        "types.py",
    } <= names


@pytest.mark.parametrize("path", python_files(LLM_DIR), ids=lambda p: p.name)
def test_the_llm_package_depends_only_on_the_domain_and_itself(path: Path) -> None:
    bad = [
        module
        for module in app_imports(path.read_text(encoding="utf-8"))
        if not (under(module, "app.domain") or under(module, "app.llm"))
    ]

    assert bad == []


@pytest.mark.parametrize("path", python_files(LLM_DIR), ids=lambda p: p.name)
def test_the_llm_package_imports_no_vendor_sdk_and_no_network_library(path: Path) -> None:
    top_level = {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}
    allowed = {"openai"} if path.name == OPENAI_TRANSPORT else set()

    assert (top_level & SDKS_AND_NETWORK) - allowed == set()


def test_only_the_transport_module_imports_the_openai_sdk() -> None:
    importers = sorted(
        path.relative_to(APP_DIR).as_posix()
        for path in python_files(APP_DIR)
        if "openai" in {m.split(".")[0] for m in imported_modules(path.read_text(encoding="utf-8"))}
    )

    assert importers == [f"llm/{OPENAI_TRANSPORT}"]


def test_the_transport_module_imports_nothing_from_the_network_family_but_the_sdk() -> None:
    source = (LLM_DIR / OPENAI_TRANSPORT).read_text(encoding="utf-8")
    top_level = {m.split(".")[0] for m in imported_modules(source)}

    assert top_level & (SDKS_AND_NETWORK - {"openai"}) == set()


def test_no_llm_code_can_reach_booking_or_approval_logic() -> None:
    reachable = {
        m for path in python_files(LLM_DIR) for m in app_imports(path.read_text(encoding="utf-8"))
    }

    assert not [m for m in reachable if "booking" in m or "approval" in m or "quote" in m]


@pytest.mark.parametrize("package", ["domain", "providers", "tools"])
def test_nothing_below_the_llm_layer_depends_on_it(package: str) -> None:
    offenders = [
        path.name
        for path in python_files(APP_DIR / package)
        if any(under(m, "app.llm") for m in app_imports(path.read_text(encoding="utf-8")))
    ]

    assert offenders == []


def test_only_the_approved_vendor_sdks_are_declared_as_dependencies() -> None:
    pyproject = (APP_DIR.parent / "pyproject.toml").read_text(encoding="utf-8").lower()

    assert "openai" in pyproject  # approved by the owner on 2026-10-30
    assert "langgraph" in pyproject  # approved by the owner on 2026-10-30 (M7)
    for sdk in ("anthropic", "langchain"):
        # LangChain's core library arrives only as LangGraph's own dependency, never declared.
        assert sdk not in pyproject, sdk
