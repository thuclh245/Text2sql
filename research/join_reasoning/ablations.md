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
- A1, A2, and A3 must each show a >= 5 percentage point EX drop on the
  targeted slice resolved by the Phase 7B ablation gate.
- Primary target slices:
  - A1: `multiple_fk_ambiguity`
  - A2: `grain_sensitive_aggregation`, `fanout_aggregation`, or `aggregation_query`
    when available; fallback is `join_depth=2+_joins` / `table_slice=multi_table`.
  - A3: `bridge_table_required`
- Run the gate with `chatsql analysis phase7b-ablation-gate --relationship-aware-run
  <run> --a1-run <run> --a2-run <run> --a3-run <run> --output-dir <dir>`.
- Configs implementing each ablation's reasoner toggle:
  `configs/experiments/relationship_ablation_a1_no_role_disambiguation.yaml`,
  `..._a2_no_grain_validation.yaml`, `..._a3_no_bridge_expansion.yaml`.

## Execution Status (2026-09-05)

Run against the real 500-case BIRD Mini-Dev SQLite benchmark with a
deterministic stub LLM (no API key available in this environment — see
`decision.md`'s Execution Status section for the full caveat). Because every
system emits the same placeholder SQL text, **EX-based deltas are exactly
zero for all three ablations and prove nothing** — the >=5pp EX-drop success
criterion above still requires a real `gpt-4o-mini` run to evaluate.

What *is* real: the relationship-reasoning quality metrics (computed from the
deterministic join-path plan against real gold SQL, independent of the LLM)
moved in the expected direction for two of the three ablations:

| Ablation | Metric | relationship_aware | Ablation | Delta | Matches prediction? |
|---|---|---:|---:|---:|---|
| A1 no-role-disambiguation | edge_recall | 0.6025 | 0.5598 | -0.0427 | yes — worse edge selection without semantic scoring |
| A1 no-role-disambiguation | wrong_edge_rate | 0.6989 | 0.7027 | +0.0038 | yes (small) |
| A2 no-grain-validation | all relationship metrics | ~0.60 / 0.89 | ~unchanged | ~0.00 | inconclusive — see note below |
| A3 no-bridge-expansion | path_coverage | 0.892 | 0.842 | -0.0500 | yes — losing bridge-required tables entirely |
| A3 no-bridge-expansion | edge_recall | 0.6025 | 0.5653 | -0.0372 | yes |

A2 showing ~zero movement is plausible rather than a red flag: grain
validation mainly reweights path scoring (the cardinality/junction-table
penalty) and prompt content, not which tables/edges are selected in the first
place, so it wouldn't be expected to move edge_recall/path_coverage much on a
general sample. Testing A2 properly needs the
`grain_sensitive_aggregation`/`fanout_aggregation` slices this document
originally called for but Phase 6B never finished defining — that is
outstanding work, not a result.

Full reports: `research/join_reasoning/phase7_execution_reports/phase7b_ablation_gate_report.md`.
