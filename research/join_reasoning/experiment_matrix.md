# Phase 6B Experiment Matrix

## Systems & Baselines Compared
| System ID | Strategy Name | Description | Role in Benchmark |
| :--- | :--- | :--- | :--- |
| **B0** | `full_schema` | Full-schema control (no join planning) | Baseline Reference |
| **B1** | `declared_fk_shortest` | Steiner-tree shortest path over declared FKs | Graph Baseline 1 |
| **B2** | `minimum_hop_heuristic` | Min-hop candidate paths + deterministic tie-break | Graph Baseline 2 |
| **B3** | `lexical_reranker` | Candidate path enumeration + lexical match | Lexical Baseline 3 |
| **CHATSQL** | `relationship_aware` | CHATSQL semantic role scoring + grain validation | Proposed Contribution |

## Controlled Variables
- **Benchmark**: `bird_mini_dev_sqlite_select_500` (pinned commit `b3d4bcb`)
- **Generator Model**: `gpt-4o-mini` (temperature `0.0`, seed `42`)
- **Evaluator**: Official BIRD EX evaluator
- **Execution Engine**: Read-only SQLite with 30.0s timeout and 10,000 row limit

## Target Slices
1. `single_table`: 0-hop control slice
2. `1_hop_join`: 2 tables joined
3. `2_hop_join`: 3 tables joined
4. `3_plus_hop_join`: >= 4 tables joined
5. `multiple_fk_ambiguity`: table pairs with >= 2 distinct FK connections
6. `bridge_table_required`: multi-table queries requiring junction/bridge tables
