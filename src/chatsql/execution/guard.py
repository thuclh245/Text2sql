"""Shared read-only SQL guard.

One place decides whether a statement is a safe, single, read-only query.
Both the benchmark loader (filtering gold) and the executor (blocking writes)
call this so the two never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Statement/segment types that mutate data or schema, or that sqlglot cannot
# model precisely enough to trust (Command covers PRAGMA, ATTACH, VACUUM, ...).
_WRITE_EXPRESSIONS: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
)

REJECTED_MULTIPLE = "multiple SQL statements are not allowed"
REJECTED_WRITE = "write or DDL statement rejected by read-only guard"


@dataclass(frozen=True)
class GuardVerdict:
    """Outcome of inspecting one SQL string."""

    ok: bool
    reason: str | None = None
    is_parse_error: bool = False


def inspect_read_only(sql: str) -> GuardVerdict:
    """Return whether ``sql`` is a single read-only query, with a reason if not."""
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as exc:
        return GuardVerdict(ok=False, reason=f"SQL parse error: {exc}", is_parse_error=True)

    parsed = [stmt for stmt in statements if stmt is not None]
    if not parsed:
        return GuardVerdict(
            ok=False, reason="SQL parse error: empty statement", is_parse_error=True
        )
    if len(parsed) > 1:
        return GuardVerdict(ok=False, reason=REJECTED_MULTIPLE)

    root = parsed[0]
    if not isinstance(root, exp.Query):
        return GuardVerdict(ok=False, reason=REJECTED_WRITE)
    if any(root.find(kind) for kind in _WRITE_EXPRESSIONS):
        return GuardVerdict(ok=False, reason=REJECTED_WRITE)
    return GuardVerdict(ok=True)


def is_read_only_select(sql: str) -> bool:
    """True if ``sql`` is a single read-only query."""
    return inspect_read_only(sql).ok
