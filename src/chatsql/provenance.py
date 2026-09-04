"""Content hashing helpers used for run provenance (dataset, evaluator, configs)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 65536


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, or ``"missing"`` if absent."""
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short_hash(digest: str, length: int = 12) -> str:
    """Shorten a hex digest for display; pass non-hex values through unchanged."""
    if digest in ("missing", "unknown", "") or len(digest) <= length:
        return digest
    return digest[:length]
