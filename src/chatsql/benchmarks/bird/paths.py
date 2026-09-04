"""Path constants for the BIRD Mini-Dev dataset.

All paths are relative to the third_party/mini_dev root, or can be resolved
via the repo root.  Use BirdPaths.resolve() to get absolute paths at runtime.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# BIRD Mini-Dev data format (from inspection of mini_dev_prompt.jsonl)
# ---------------------------------------------------------------------------
# Each record in the question JSON has:
#   question_id   : int
#   db_id         : str
#   question      : str
#   evidence      : str   (business-rule hint)
#   SQL           : str   (gold SQL — must be separated during load)
#   difficulty    : "simple" | "moderate" | "challenging"
#
# The DB directory layout is:
#   <db_root>/<db_id>/<db_id>.sqlite
# ---------------------------------------------------------------------------


class BirdPaths:
    """Centralises all BIRD dataset path logic."""

    def __init__(self, mini_dev_root: Path) -> None:
        self.root = mini_dev_root.resolve()

    @classmethod
    def from_repo_root(cls, repo_root: Path | None = None) -> BirdPaths:
        """Construct from the chatsql repository root directory."""
        if repo_root is None:
            # Walk up from this file until we find pyproject.toml
            here = Path(__file__).resolve()
            for parent in here.parents:
                if (parent / "pyproject.toml").exists():
                    repo_root = parent
                    break
            else:
                raise RuntimeError("Cannot locate repo root (pyproject.toml not found)")
        return cls(repo_root / "third_party" / "mini_dev")

    # ------------------------------------------------------------------
    # Data files (user must download separately — see configs/benchmarks/)
    # ------------------------------------------------------------------

    @property
    def data_dir(self) -> Path:
        """Root of the downloaded BIRD data (contains question JSON + DBs)."""
        return self.root / "llm" / "mini_dev_data"

    def question_json(self, split: str = "mini_dev_sqlite") -> Path:
        """Path to the questions JSON file for the given split."""
        return self.data_dir / f"{split}.json"

    def db_root(self) -> Path:
        """Root directory containing per-database subdirectories."""
        return self.data_dir / "databases"

    def sqlite_path(self, db_id: str) -> Path:
        """Path to the .sqlite file for a given database ID."""
        return self.db_root() / db_id / f"{db_id}.sqlite"

    # ------------------------------------------------------------------
    # Evaluator (comes with the git clone)
    # ------------------------------------------------------------------

    @property
    def evaluator_dir(self) -> Path:
        return self.root / "evaluation"

    @property
    def evaluation_ex_py(self) -> Path:
        return self.evaluator_dir / "evaluation_ex.py"

    @property
    def evaluation_utils_py(self) -> Path:
        return self.evaluator_dir / "evaluation_utils.py"
