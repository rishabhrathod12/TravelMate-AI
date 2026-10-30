"""How checkpoints are written and, above all, read back (ARCHITECTURE §8, SECURITY §10).

A checkpoint holds the run's state. When a checkpoint is read, the serializer rebuilds Python
objects from stored data, and by default it would rebuild any class the data names. Once
checkpoints live in a database (M9) that is a code-execution path for anyone who can write a row.
So the serializer is given an explicit allowlist: only this project's own data types
(domain models and enums, tool results, the conversation draft and the workflow state) are rebuilt.
Anything else is blocked and comes back as plain data, never as an object.

The list is built from the modules, not typed by hand, so a new domain type is covered without a
second edit. Types outside these modules are never added automatically.
"""

import importlib
import pkgutil
from enum import Enum

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

import app.domain

# Modules whose data types may be rebuilt from a checkpoint.
_EXTRA_MODULES = (
    "app.tools.results",
    "app.conversation.draft",
    "app.workflow.state",
)


def _domain_modules() -> list[str]:
    return [
        f"app.domain.{module.name}"
        for module in pkgutil.iter_modules(app.domain.__path__)
        if not module.name.startswith("_")
    ]


def allowed_types() -> list[tuple[str, str]]:
    """Every project data type (model or enum) that a checkpoint may rebuild, sorted."""
    allowed: set[tuple[str, str]] = set()
    for module_name in [*_domain_modules(), *_EXTRA_MODULES]:
        module = importlib.import_module(module_name)
        for name, value in vars(module).items():
            is_class = isinstance(value, type)
            if (
                is_class
                and value.__module__ == module_name
                and issubclass(value, BaseModel | Enum)
                and not name.startswith("_")
            ):
                allowed.add((module_name, name))
    return sorted(allowed)


def checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=allowed_types())


def new_checkpointer() -> InMemorySaver:
    """The in-memory checkpointer used until persistence exists (M9)."""
    return InMemorySaver(serde=checkpoint_serializer())
