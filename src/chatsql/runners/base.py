"""Base class for baseline process runners.

Provides process isolation for executing external baseline code without polluting
the main CHATSQL runtime environment.
"""

from __future__ import annotations

import abc
from pathlib import Path


class BaseRunner(abc.ABC):
    """Abstract baseline runner."""

    @abc.abstractmethod
    def run(
        self,
        command: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> tuple[int, str, str]:
        """Run command and return (exit_code, stdout, stderr)."""
        ...
