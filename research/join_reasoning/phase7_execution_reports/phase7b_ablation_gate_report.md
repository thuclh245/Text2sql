# Phase 7B Ablation Gate Report

- **Full relationship-aware system:** `relationship_aware` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T125650Z_29336c)
- **Targeted drop threshold:** 5.00pp
- **Gate Status:** **FAIL**

## Targeted Drops
| Ablation | Target Slice | Relationship Aware | Ablation | Drop | Passed |
|---|---|---:|---:|---:|:---:|
| `A1` A1_no_role_disambiguation | `join_relationship=multiple_fk_ambiguity` | 2.90 | 2.90 | -0.00 | no |
| `A2` A2_no_grain_validation | `join_depth=2+_joins` | 1.94 | 1.94 | -0.00 | no |
| `A3` A3_no_bridge_expansion | `join_relationship=bridge_table_required` | 2.15 | 2.15 | -0.00 | no |

## Overall EX
| Ablation | Relationship Aware | Ablation | Delta | Cases |
|---|---:|---:|---:|---:|
| `A1` A1_no_role_disambiguation | 3.00 | 3.00 | +0.00 | 500 / 500 |
| `A2` A2_no_grain_validation | 3.00 | 3.00 | +0.00 | 500 / 500 |
| `A3` A3_no_bridge_expansion | 3.00 | 3.00 | +0.00 | 500 / 500 |

## Relationship Metrics
| Ablation | Metric | Relationship Aware | Ablation | Delta |
|---|---|---:|---:|---:|
| `A1` | `relationship_total` | 500.0 | 500.0 | +0.0000 |
| `A1` | `relationship_edge_recall` | 0.6025 | 0.5598 | -0.0427 |
| `A1` | `relationship_edge_precision` | 0.2671 | 0.2633 | -0.0038 |
| `A1` | `relationship_wrong_edge_rate` | 0.6989 | 0.7027 | +0.0038 |
| `A1` | `relationship_path_coverage` | 0.892 | 0.89 | -0.0020 |
| `A1` | `relationship_exact_path_accuracy` | 0.114 | 0.114 | +0.0000 |
| `A1` | `relationship_mean_hop_count` | 3.97 | 3.75 | -0.2200 |
| `A2` | `relationship_total` | 500.0 | 500.0 | +0.0000 |
| `A2` | `relationship_edge_recall` | 0.6025 | 0.6032 | +0.0007 |
| `A2` | `relationship_edge_precision` | 0.2671 | 0.2667 | -0.0004 |
| `A2` | `relationship_wrong_edge_rate` | 0.6989 | 0.6993 | +0.0004 |
| `A2` | `relationship_path_coverage` | 0.892 | 0.892 | +0.0000 |
| `A2` | `relationship_exact_path_accuracy` | 0.114 | 0.114 | +0.0000 |
| `A2` | `relationship_mean_hop_count` | 3.97 | 3.99 | +0.0200 |
| `A3` | `relationship_total` | 500.0 | 500.0 | +0.0000 |
| `A3` | `relationship_edge_recall` | 0.6025 | 0.5653 | -0.0372 |
| `A3` | `relationship_edge_precision` | 0.2671 | 0.2848 | +0.0177 |
| `A3` | `relationship_wrong_edge_rate` | 0.6989 | 0.6512 | -0.0477 |
| `A3` | `relationship_path_coverage` | 0.892 | 0.842 | -0.0500 |
| `A3` | `relationship_exact_path_accuracy` | 0.114 | 0.14 | +0.0260 |
| `A3` | `relationship_mean_hop_count` | 3.97 | 3.4 | -0.5700 |
