# Hypothesis: H02 Relationship, Join-Path, and Grain Reasoning

## Observation
In baseline Text-to-SQL generation (full schema control), error analysis demonstrates that despite correct table identification (retrieval recall > 90%), failures frequently occur on multi-table joins due to wrong join keys, inverted foreign keys, missing bridge tables, and aggregation fan-out on non-primary grains.

## Prior evidence
- BIRD benchmark multi-table join difficulty distribution (`docs/16_SOURCES_AND_EVIDENCE.md`).
- DIN-SQL and CHESS studies noting join role ambiguity and multi-hop decomposition failures as leading causes of execution error.
- Architecture specification in `docs/overview/08_RELATIONSHIP_JOIN_REASONING.md` and `docs/phase/P6B_JOIN_RELATIONSHIP_RESEARCH.md`.

## Hypothesis
Explicit multi-hop relationship path planning, foreign-key role disambiguation, and query entity grain validation in prompt context will increase Execution Accuracy (EX) on multi-table join queries in BIRD Mini-Dev SQLite by at least 2.5 percentage points compared to the modernized full-schema baseline without decreasing accuracy on single-table queries.

## Changed component
- `strategy`: `relationship_aware` with `SemanticRelationshipReasoner` and `RelationshipAwarePromptBuilder`.

## Fixed components
- Benchmark split: `bird_mini_dev_sqlite_select_500` (pinned commit `b3d4bcbbae9a96934ad812551eb400c7a3b23c12`).
- Model: `gpt-4o-mini` (revision `2024-07-18`, temperature `0.0`).
- Evaluator: Official BIRD execution evaluator (`evaluation_ex.py`).
- Seed: `42`.

## Dataset / subset
- Full BIRD Mini-Dev SQLite (500 select queries).
- Diagnostic join slices: 1-hop, 2-hop, 3+ hop, multiple FK ambiguity, and bridge-table required queries.

## Primary metric
- Downstream Execution Accuracy (EX) on multi-table join queries.

## Secondary metrics
- Edge recall and precision.
- Wrong-edge rate.
- Exact join-path accuracy.
- EX on single-table queries (safety/non-regression check).

## Expected mechanism
Providing the generator with pre-disambiguated foreign-key join predicates and explicit target query grain resolves role ambiguities (e.g. distinguishing origin vs destination airports) and prevents Cartesian duplication.

## Failure criterion
Reject hypothesis if multi-table join EX does not improve by at least 1.0 percentage points, or if single-table query EX regresses by more than 1.0 percentage points.

## Ablations
1. Disable role disambiguation (fallback to shortest-path Steiner tree).
2. Disable grain/cardinality validation.
3. Disable bridge table expansion.

## Risks / confounders
- Graph incompleteness when schemas lack declared foreign keys.
- Context length increase from relationship instructions.

## Decision after experiment
- [ ] supported
- [ ] rejected
- [ ] inconclusive
