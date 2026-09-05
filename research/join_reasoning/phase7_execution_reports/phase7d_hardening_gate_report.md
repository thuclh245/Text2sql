# Phase 7D Targeted Hardening Gate Report

- **Before:** `before_hardening` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T124819Z_746888)
- **After:** `after_hardening` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T125650Z_29336c)
- **Target slice:** `single_table`
- **Gate Status:** **PASS**

## Gate Criteria
| Criterion | Passed |
|---|:---:|
| Target slice quality improved | yes |
| No other slice regressed > 1.00% | yes |

## Relationship Quality by Slice (Before -> After)
| Slice | Cases (before/after) | Quality Before | Quality After | Delta |
|---|---:|---:|---:|---:|
| `single_table` **<- target** | 86 / 86 | 0.3256 | 0.4264 | +0.1008 |
| `1_hop_join` | 252 / 252 | 0.6181 | 0.6409 | +0.0229 |
| `2_hop_join` | 0 / 0 | 0.3333 | 0.3333 | +0.0000 |
| `3_plus_hop_join` | 0 / 0 | 0.3333 | 0.3333 | +0.0000 |
| `multiple_fk_ambiguity` | 69 / 69 | 0.5380 | 0.5561 | +0.0181 |
| `bridge_table_required` | 93 / 93 | 0.6439 | 0.6743 | +0.0304 |
