"""Config loader — reads YAML config files and validates them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML config file and return as a plain dict."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must be a YAML mapping, got {type(data)}: {path}")
    return data


def config_hash(config: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hash of a config dict."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_and_hash(path: Path) -> tuple[dict[str, Any], str]:
    """Load a YAML config and return (config_dict, hash)."""
    cfg = load_yaml(path)
    return cfg, config_hash(cfg)
