# Phase 6B Ablations Plan

## Ablation Design
To verify that gains originate from relationship and grain reasoning rather than confounding variables, the following ablations are isolated:

1. **No-Role-Disambiguation (A1)**:
   - Sets edge scoring to uniform distance (shortest path).
   - Expected drop on `multiple_fk_ambiguity` slice.
2. **No-Grain-Validation (A2)**:
   - Disables cardinality penalty and grain hints in prompt.
   - Expected increase in fan-out and duplicate count errors on aggregation queries.
3. **No-Bridge-Expansion (A3)**:
   - Disallows intermediate tables during path generation.
   - Expected failure on `bridge_table_required` slice.

## Success Criteria for Ablations
- A1, A2, and A3 must show statistically noticeable drops in accuracy on their respective target slices.
