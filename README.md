# CHATSQL

Research-first Text-to-SQL system. The repository starts with a lightweight core
Python environment; heavyweight published baselines must live in isolated Conda or
Docker environments.

## Setup

```bash
make install
make test
```

Useful commands:

```bash
make test
make lint
make typecheck
```

## Relationship-Aware Grounding Research

The `relationship-aware` schema grounder ranks tables and columns from
question/evidence tokens, expands selected tables through declared foreign-key
relationships, and keeps key columns needed for joins in the grounded schema.

Smoke-check the wiring without calling a model:

```bash
chatsql experiment run \
  --benchmark bird_mini_dev_sqlite_select_500 \
  --strategy full_schema \
  --config configs/experiments/relationship_aware_grounding_research.yaml \
  --dry-run
```

Estimate prompt cost before a run:

```bash
chatsql experiment estimate-tokens \
  --benchmark bird_mini_dev_sqlite_select_500 \
  --strategy full_schema \
  --config configs/experiments/relationship_aware_grounding_research.yaml
```

Run a small smoke experiment:

```bash
chatsql experiment run \
  --benchmark bird_mini_dev_sqlite_select_500 \
  --strategy full_schema \
  --config configs/experiments/relationship_aware_grounding_research.yaml \
  --limit 5
```
