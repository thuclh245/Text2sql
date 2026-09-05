# Phase 7D Relationship Slice-Quality Report

- **Run:** `relationship_aware` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T125650Z_29336c)

## Relationship Quality by Join Slice
| Slice | Cases | Edge Recall | Edge Precision | Wrong-Edge Rate | Path Coverage | Exact Path | Mean Hops | Quality Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `single_table` | 86 | 0.1512 | 0.1512 | 0.8488 | 0.9767 | 0.1512 | 2.92 | 0.4264 |
| `1_hop_join` | 252 | 0.7183 | 0.2998 | 0.6526 | 0.8571 | 0.1468 | 3.63 | 0.6409 |
| `2_hop_join` | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.3333 |
| `3_plus_hop_join` | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.3333 |
| `multiple_fk_ambiguity` | 69 | 0.5072 | 0.1901 | 0.8099 | 0.9710 | 0.0725 | 4.74 | 0.5561 |
| `bridge_table_required` | 93 | 0.7769 | 0.3429 | 0.6034 | 0.8495 | 0.0215 | 5.29 | 0.6743 |

## Bottleneck
- **Weakest slice:** `single_table` (quality score 0.4264, 86 cases).
- Phase 7D hardening should target this slice, then rerun and compare with `phase7d-hardening-gate`.
