"""SQL output parser - extracts the final SQL statement from a raw LLM response.

Handles:
  - ```sql ... ``` fenced blocks (takes the last one; chain-of-thought may emit several)
  - a bare SELECT / WITH statement embedded in prose

The raw response is always kept by the caller for auditing; this only lifts out
the statement to execute.
"""

from __future__ import annotations

import re

_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_SQL_START_RE = re.compile(r"((?:WITH|SELECT)\b.*)", re.DOTALL | re.IGNORECASE)


def extract_sql(raw_text: str) -> str | None:
    """Extract the SQL statement from raw LLM text, or ``None`` if none is present."""
    blocks = _SQL_FENCE_RE.findall(raw_text)
    if blocks:
        candidate = blocks[-1].strip()
        if candidate.upper().startswith(("SELECT", "WITH")):
            return _clean(candidate)

    match = _SQL_START_RE.search(raw_text)
    if match:
        return _clean(_first_statement(match.group(1)))

    return None


def _first_statement(text: str) -> str:
    """Trim trailing prose: stop at a fence, a blank line, or the first ``;``."""
    for terminator in ("```", "\n\n"):
        index = text.find(terminator)
        if index != -1:
            text = text[:index]
    semicolon = text.find(";")
    if semicolon != -1:
        text = text[: semicolon + 1]
    return text


def _clean(sql: str) -> str:
    """Normalise whitespace and drop a trailing fence or semicolon."""
    sql = sql.strip().removesuffix("```").strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql
