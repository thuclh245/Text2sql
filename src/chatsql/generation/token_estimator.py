"""Prompt token estimation helpers.

Use provider tokenizers when they are installed; otherwise fall back to a
conservative character-based estimate so experiments can still run offline.
"""

from __future__ import annotations

import math


def estimate_text_tokens(text: str, model: str | None = None) -> int:
    """Estimate token count for plain text."""
    token_count = _estimate_with_tiktoken(text, model)
    if token_count is not None:
        return token_count
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_chat_prompt_tokens(prompt: str, model: str | None = None) -> int:
    """Estimate tokens for one user-message chat completion request."""
    content_tokens = estimate_text_tokens(prompt, model)
    # Small fixed overhead for role/message wrappers in Chat Completions.
    return content_tokens + 4


def _estimate_with_tiktoken(text: str, model: str | None) -> int | None:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        encoding = tiktoken.encoding_for_model(model or "gpt-4o-mini")
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    return len(encoding.encode(text))
