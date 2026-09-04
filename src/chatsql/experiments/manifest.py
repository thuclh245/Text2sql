"""ExperimentManifest — captures everything needed to reproduce a run."""

from __future__ import annotations

import datetime
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Sub-sections
# ---------------------------------------------------------------------------


class ExperimentMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    timestamp: datetime.datetime
    seed: int
    git_commit: str


class BenchmarkMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    revision: str
    data_hash: str
    evaluator_revision: str


class SystemMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy: str
    config_hash: str
    upstream_commit: str


class ModelMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    name: str
    revision: str
    temperature: float


class EnvironmentMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    python: str
    os: str
    dependency_lock_hash: str


# ---------------------------------------------------------------------------
# ExperimentManifest
# ---------------------------------------------------------------------------


class ExperimentManifest(BaseModel):
    """Frozen manifest capturing all reproducibility metadata for one run."""

    model_config = ConfigDict(frozen=True)

    experiment: ExperimentMeta
    benchmark: BenchmarkMeta
    system: SystemMeta
    model: ModelMeta
    environment: EnvironmentMeta

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (deterministic key order)."""
        raw = self.model_dump()
        # datetime → ISO string
        raw["experiment"]["timestamp"] = raw["experiment"]["timestamp"].isoformat()
        return raw

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string (sorted keys)."""
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> ExperimentManifest:
        data = json.loads(text)
        data["experiment"]["timestamp"] = datetime.datetime.fromisoformat(
            data["experiment"]["timestamp"]
        )
        return cls(**data)

    def manifest_hash(self) -> str:
        """SHA-256 of the canonical JSON representation."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _get_git_commit(repo_root: Path | None = None) -> str:
    """Return the current HEAD commit hash, or 'unknown'."""
    try:
        cwd = str(repo_root) if repo_root else None
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _hash_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file, or 'missing' if not found."""
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_config(config: dict[str, Any] | None) -> str:
    """Stable hash of an arbitrary config dict (sorted keys)."""
    if config is None:
        return hashlib.sha256(b"{}").hexdigest()
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_manifest(
    *,
    experiment_id: str,
    seed: int,
    benchmark_name: str,
    benchmark_revision: str,
    benchmark_data_hash: str,
    evaluator_revision: str,
    strategy_name: str,
    strategy_config: dict[str, Any] | None = None,
    upstream_commit: str = "unknown",
    model_provider: str,
    model_name: str,
    model_revision: str,
    model_temperature: float,
    repo_root: Path | None = None,
    lock_file: Path | None = None,
) -> ExperimentManifest:
    """Convenience factory that auto-detects git commit and environment."""
    git_commit = _get_git_commit(repo_root)

    # Dependency lock hash
    lock_hash = "missing"
    if lock_file is not None:
        lock_hash = _hash_file(lock_file)
    else:
        # Try to find uv.lock or requirements.lock next to pyproject.toml
        base_dir = repo_root if repo_root is not None else Path.cwd()
        candidates = [
            base_dir / "uv.lock",
            base_dir / "requirements.lock",
            base_dir / "poetry.lock",
        ]
        for c in candidates:
            if c.exists():
                lock_hash = _hash_file(c)
                break

    return ExperimentManifest(
        experiment=ExperimentMeta(
            id=experiment_id,
            timestamp=datetime.datetime.now(datetime.UTC),
            seed=seed,
            git_commit=git_commit,
        ),
        benchmark=BenchmarkMeta(
            name=benchmark_name,
            revision=benchmark_revision,
            data_hash=benchmark_data_hash,
            evaluator_revision=evaluator_revision,
        ),
        system=SystemMeta(
            strategy=strategy_name,
            config_hash=_hash_config(strategy_config),
            upstream_commit=upstream_commit,
        ),
        model=ModelMeta(
            provider=model_provider,
            name=model_name,
            revision=model_revision,
            temperature=model_temperature,
        ),
        environment=EnvironmentMeta(
            python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            os=f"{platform.system()} {platform.release()}",
            dependency_lock_hash=lock_hash,
        ),
    )
