"""CHATSQL — Research-first Text-to-SQL framework.

Sub-packages:
    chatsql.domain       — Immutable data contracts (InferenceCase, GoldCase, …)
    chatsql.experiments  — Manifest, RunLogger, BaseStrategy, ExperimentRunner
    chatsql.evaluation   — BaseEvaluator (gold-aware layer)
    chatsql.config       — YAML loader + deterministic config hash
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
