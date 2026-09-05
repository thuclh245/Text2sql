# Phase 7D Relationship Slice-Quality Report

- **Run:** `relationship_aware` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T124819Z_746888)

## Relationship Quality by Join Slice
| Slice | Cases | Edge Recall | Edge Precision | Wrong-Edge Rate | Path Coverage | Exact Path | Mean Hops | Quality Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `single_table` | 86 | 0.0000 | 0.0000 | 1.0000 | 0.9767 | 0.0000 | 5.08 | 0.3256 |
| `1_hop_join` | 252 | 0.7421 | 0.2034 | 0.7966 | 0.9087 | 0.0000 | 5.29 | 0.6181 |
| `2_hop_join` | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.3333 |
| `3_plus_hop_join` | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.3333 |
| `multiple_fk_ambiguity` | 69 | 0.5217 | 0.0922 | 0.9078 | 1.0000 | 0.0000 | 6.67 | 0.5380 |
| `bridge_table_required` | 93 | 0.7796 | 0.2596 | 0.7404 | 0.8925 | 0.0108 | 7.28 | 0.6439 |

## Bottleneck
- **Weakest slice:** `single_table` (quality score 0.3256, 86 cases).
- Phase 7D hardening should target this slice, then rerun and compare with `phase7d-hardening-gate`.
