# Phase 7A Benchmark Gate Report

- **Full-schema control:** `full_schema` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/full_schema_control_20260905T124649Z_7d8e54)
- **Relationship-aware candidate:** `relationship_aware` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T125650Z_29336c)
- **Gate Status:** **FAIL**

## Overall EX
| System | Total | Correct | EX (%) |
|---|---:|---:|---:|
| full_schema | 500 | 15 | 3.00 |
| relationship_aware | 500 | 15 | 3.00 |
| Delta |  |  | +0.00 |

## Gate Criteria
| Criterion | Passed |
|---|:---:|
| Join-heavy slice EX improves | no |
| Single-table regression within < 1.0% tolerance | yes |
| Relationship metrics improve | yes |

## Slice EX
| Slice Dimension | Slice | Full Schema | Relationship Aware | Delta | Cases |
|---|---|---:|---:|---:|---:|
| `difficulty` | `unspecified` | 3.00 | 3.00 | +0.00 | 500 / 500 |
| `execution_failure` | `False` | 3.00 | 3.00 | +0.00 | 500 / 500 |
| `high_noise_retrieval` | `False` | 3.00 | 3.00 | +0.00 | 500 / 500 |
| `join_depth` | `0_joins` | 4.30 | 4.30 | +0.00 | 93 / 93 |
| `join_depth` | `1_join` | 2.96 | 2.96 | +0.00 | 304 / 304 |
| `join_depth` | `2+_joins` | 1.94 | 1.94 | +0.00 | 103 / 103 |
| `join_relationship` | `1_hop_join` | 2.78 | 2.78 | +0.00 | 252 / 252 |
| `join_relationship` | `bridge_table_required` | 2.15 | 2.15 | +0.00 | 93 / 93 |
| `join_relationship` | `multiple_fk_ambiguity` | 2.90 | 2.90 | +0.00 | 69 / 69 |
| `join_relationship` | `single_table` | 4.65 | 4.65 | +0.00 | 86 / 86 |
| `schema_size` | `medium (6-15 tables)` | 0.00 | 2.29 | +2.29 | 0 / 350 |
| `schema_size` | `small (<=5 tables)` | 0.00 | 4.67 | +4.67 | 0 / 150 |
| `schema_size` | `unknown` | 3.00 | 0.00 | -3.00 | 500 / 0 |
| `table_slice` | `multi_table` | 2.70 | 2.70 | +0.00 | 407 / 407 |
| `table_slice` | `single_table` | 4.30 | 4.30 | +0.00 | 93 / 93 |

## Relationship Metrics
| Metric | Full Schema | Relationship Aware | Delta |
|---|---:|---:|---:|
| `relationship_total` | 0.0 | 500.0 | +500.0000 |
| `relationship_edge_recall` | 0.0 | 0.6025 | +0.6025 |
| `relationship_edge_precision` | 0.0 | 0.2671 | +0.2671 |
| `relationship_wrong_edge_rate` | 0.0 | 0.6989 | +0.6989 |
| `relationship_path_coverage` | 0.0 | 0.892 | +0.8920 |
| `relationship_exact_path_accuracy` | 0.0 | 0.114 | +0.1140 |
| `relationship_mean_hop_count` | 0.0 | 3.97 | +3.9700 |
