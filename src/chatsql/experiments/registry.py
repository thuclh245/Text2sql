"""Strategy registry — maps strategy names to their classes."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatsql.experiments.runner import BaseStrategy

StrategyType = type["BaseStrategy"]
StrategyDecorator = Callable[[StrategyType], StrategyType]

_REGISTRY: dict[str, StrategyType] = {}


def register(name: str) -> StrategyDecorator:
    """Class decorator to register a strategy under a given name."""

    def decorator(cls: StrategyType) -> StrategyType:
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_strategy(name: str) -> StrategyType:
    """Return a registered strategy class by name."""
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys())) or "<none registered>"
        raise KeyError(f"Strategy '{name}' not found. Available: {available}")
    return _REGISTRY[name]


def list_strategies() -> list[str]:
    """Return sorted list of all registered strategy names."""
    return sorted(_REGISTRY.keys())
