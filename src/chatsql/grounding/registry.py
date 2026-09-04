"""Registry for Schema Grounder components."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from chatsql.grounding.base import SchemaGrounder

_GROUNDER_REGISTRY: dict[str, type[SchemaGrounder]] = {}

T = TypeVar("T", bound=type[SchemaGrounder])


def register_grounder(name: str) -> Callable[[T], T]:
    """Decorator to register a SchemaGrounder class under a string name."""

    def decorator(cls: T) -> T:
        if name in _GROUNDER_REGISTRY:
            raise ValueError(f"Grounder '{name}' is already registered.")
        _GROUNDER_REGISTRY[name] = cls
        return cls

    return decorator


def get_grounder(name: str) -> type[SchemaGrounder]:
    """Retrieve a registered SchemaGrounder class by name."""
    if name not in _GROUNDER_REGISTRY:
        available = ", ".join(sorted(_GROUNDER_REGISTRY.keys())) or "none"
        raise KeyError(f"Grounder '{name}' not found. Available: {available}")
    return _GROUNDER_REGISTRY[name]


def list_grounders() -> list[str]:
    """List all registered grounder names."""
    return sorted(_GROUNDER_REGISTRY.keys())
