"""Architecture rule: `domain/` imports nothing from other `app` packages.

See docs/ARCHITECTURE.md §3 (dependency rules) and plan M2 completion criteria.
"""

import ast
from pathlib import Path

import pytest

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "app" / "domain"


def forbidden_imports(source: str) -> list[str]:
    """Return imports that reach `app` outside `app.domain`.

    Relative imports that climb out of the current package are rejected too.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 1:
                found.append("." * node.level + (node.module or ""))
                continue
            if node.level == 1:
                continue
            modules = [node.module or ""]
        else:
            continue
        for module in modules:
            is_app = module == "app" or module.startswith("app.")
            in_domain = module == "app.domain" or module.startswith("app.domain.")
            if is_app and not in_domain:
                found.append(module)
    return found


@pytest.mark.parametrize(
    "source",
    [
        "import json\nfrom datetime import date\nfrom pydantic import BaseModel",
        "from app.domain.base import DomainModel",
        "from app.domain import base",
        "from . import base",
        "from .base import DomainModel",
    ],
)
def test_allowed_imports_are_accepted(source: str) -> None:
    assert forbidden_imports(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from app.config import Settings", ["app.config"]),
        ("import app.api.health", ["app.api.health"]),
        ("from app import __version__", ["app"]),
        ("import app", ["app"]),
        ("from ..api import health", ["..api"]),
        ("from .. import config", [".."]),
    ],
)
def test_imports_of_other_app_packages_are_found(source: str, expected: list[str]) -> None:
    assert forbidden_imports(source) == expected


def test_domain_package_is_present_and_not_empty() -> None:
    # Guards against the rule passing only because it scanned nothing.
    assert (DOMAIN_DIR / "trip.py").is_file()


def test_domain_modules_do_not_import_other_app_packages() -> None:
    violations = {
        str(path.relative_to(DOMAIN_DIR)): bad
        for path in sorted(DOMAIN_DIR.rglob("*.py"))
        if (bad := forbidden_imports(path.read_text(encoding="utf-8")))
    }

    assert violations == {}
