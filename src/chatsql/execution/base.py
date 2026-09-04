"""Base executor interface."""

from __future__ import annotations

import abc

from chatsql.domain.result import ExecutionResult


class BaseExecutor(abc.ABC):
    """Abstract SQL executor."""

    @abc.abstractmethod
    def execute(self, sql: str, database_id: str, case_id: str) -> ExecutionResult:
        """Execute a SQL query and return a structured result."""
        ...
