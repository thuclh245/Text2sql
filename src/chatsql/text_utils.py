"""Shared text-processing helpers used across grounding and relationship reasoning."""

from __future__ import annotations

import re


def tokenize(text: str | None) -> set[str]:
    """Lowercase, underscore-split, alphanumeric tokenization with light plural stemming."""
    if not text:
        return set()
    tokens: set[str] = set()
    normalized = text.lower().replace("_", " ")
    for word in re.findall(r"[a-z0-9]+", normalized):
        if len(word) > 1:
            tokens.add(word)
            if len(word) > 3 and word.endswith("s"):
                tokens.add(word[:-1])
    return tokens
