"""Unit tests for ExperimentManifest (P0-T03)."""

from __future__ import annotations

import datetime
import json

from chatsql.experiments.manifest import (
    BenchmarkMeta,
    EnvironmentMeta,
    ExperimentManifest,
    ExperimentMeta,
    ModelMeta,
    SystemMeta,
    _hash_config,
    build_manifest,
)


def _make_manifest() -> ExperimentManifest:
    return ExperimentManifest(
        experiment=ExperimentMeta(
            id="exp-001",
            timestamp=datetime.datetime(2026, 1, 1, 0, 0, 0),
            seed=42,
            git_commit="abc123",
        ),
        benchmark=BenchmarkMeta(
            name="BIRD-mini-dev",
            revision="v1.0.0",
            data_hash="deadbeef",
            evaluator_revision="a1b2c3",
        ),
        system=SystemMeta(
            strategy="FullSchemaStrategy",
            config_hash="cfghash",
            upstream_commit="unknown",
        ),
        model=ModelMeta(
            provider="openai",
            name="gpt-4o-mini",
            revision="2024-07-18",
            temperature=0.0,
        ),
        environment=EnvironmentMeta(
            python="3.11.0",
            os="Linux 5.15",
            dependency_lock_hash="lockhash",
        ),
    )


class TestManifestRoundtrip:
    def test_manifest_roundtrip(self) -> None:
        """Manifest must survive JSON round-trip unchanged."""
        m = _make_manifest()
        json_str = m.to_json()
        m2 = ExperimentManifest.from_json(json_str)
        assert m2.experiment.id == m.experiment.id
        assert m2.benchmark.name == m.benchmark.name
        assert m2.model.temperature == m.model.temperature
        assert m2.environment.python == m.environment.python

    def test_manifest_hash_stable(self) -> None:
        """Same manifest must always produce the same hash."""
        m = _make_manifest()
        h1 = m.manifest_hash()
        h2 = m.manifest_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_manifest_hash_changes_on_mutation(self) -> None:
        """Different manifests must produce different hashes."""
        m1 = _make_manifest()
        # Build a variant with different seed
        m2 = ExperimentManifest(
            experiment=ExperimentMeta(
                id="exp-001",
                timestamp=datetime.datetime(2026, 1, 1, 0, 0, 0),
                seed=99,  # changed
                git_commit="abc123",
            ),
            benchmark=m1.benchmark,
            system=m1.system,
            model=m1.model,
            environment=m1.environment,
        )
        assert m1.manifest_hash() != m2.manifest_hash()

    def test_manifest_json_is_sorted(self) -> None:
        """JSON output must have deterministic (sorted) keys."""
        m = _make_manifest()
        json_str = m.to_json()
        parsed = json.loads(json_str)
        top_keys = list(parsed.keys())
        assert top_keys == sorted(top_keys)


class TestConfigHash:
    def test_hash_is_deterministic(self) -> None:
        cfg = {"model": "gpt-4", "temperature": 0.0, "max_tokens": 512}
        assert _hash_config(cfg) == _hash_config(cfg)

    def test_hash_order_independent(self) -> None:
        cfg1 = {"a": 1, "b": 2}
        cfg2 = {"b": 2, "a": 1}
        assert _hash_config(cfg1) == _hash_config(cfg2)

    def test_hash_changes_with_value(self) -> None:
        cfg1 = {"temperature": 0.0}
        cfg2 = {"temperature": 1.0}
        assert _hash_config(cfg1) != _hash_config(cfg2)


class TestBuildManifest:
    def test_build_manifest_produces_valid_object(self) -> None:
        m = build_manifest(
            experiment_id="test-run-001",
            seed=0,
            benchmark_name="BIRD",
            benchmark_revision="v1",
            benchmark_data_hash="abc",
            evaluator_revision="ev1",
            strategy_name="DummyStrategy",
            strategy_config={"dummy": True},
            model_provider="openai",
            model_name="gpt-4o-mini",
            model_revision="2024-07-18",
            model_temperature=0.0,
        )
        assert m.experiment.id == "test-run-001"
        assert m.benchmark.name == "BIRD"
        assert len(m.manifest_hash()) == 64
        assert m.environment.python != ""
        assert m.environment.os != ""
