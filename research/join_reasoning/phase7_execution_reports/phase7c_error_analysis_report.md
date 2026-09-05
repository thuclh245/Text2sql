# Phase 7C Error Analysis Report

- **Run:** `relationship_aware` (/tmp/claude-1000/-home-thuclh245-MyCode-Text2sql/d4716739-f925-4a8b-9c05-70cfd7a0dd28/scratchpad/runs_stub/relationship_path_reasoner_20260905T125650Z_29336c)
- **Total cases:** 500 (correct: 15, incorrect: 485)
- **Bridge detection:** enabled (catalogs loaded)

## Error Buckets
| Bucket | Count | % of Incorrect | Error Codes | Example Cases |
|---|---:|---:|---|---|
| Missing table | 354 | 72.99% | E01×354 | bird_1471, bird_1472, bird_1473, bird_1476, bird_1479 |
| Missing bridge table | 89 | 18.35% | E01×89 | bird_1500, bird_1501, bird_1506, bird_1514, bird_1526 |
| SQL generation despite correct plan | 42 | 8.66% | E02×42 | bird_1362, bird_1025, bird_1030, bird_1032, bird_1039 |
| Wrong FK / join path | 0 | 0.00% | - | - |
| Fanout / grain error | 0 | 0.00% | - | - |

## Bottleneck
- **Primary bottleneck:** Missing table (354 cases, 72.99% of incorrect cases).
- Phase 7D should fix this bucket first, then rerun only the slice it affects.
