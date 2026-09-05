# Phase 6B Exit Gate Decision

## Status: IMPLEMENTED & READY FOR BENCHMARK EXECUTION

## Verification Checklist
- [x] Typed `RelationshipEdge` and `RelationshipPlan` data models implemented.
- [x] Multi-edge `SchemaRelationshipGraph` supporting FK path resolution and bridge discovery.
- [x] Baseline path finders (Shortest path, Min-hop heuristic, Lexical reranker) implemented.
- [x] `SemanticRelationshipReasoner` with role disambiguation and grain validation implemented.
- [x] Diagnostic join slices (`1_hop`, `2_hop`, `3_plus_hop`, `multiple_fk`, `bridge_table`) implemented.
- [x] Relationship evaluation metrics (`edge_recall`, `edge_precision`, `wrong_edge_rate`, `path_coverage`) implemented.
- [x] `RelationshipAwareStrategy` registered and exposed to CLI.
- [x] Formal hypothesis `H02` authored.
- [x] Unit test suite passing 100% with no regressions.

## Exit Gate Criteria
1. Join-heavy slices demonstrate EX improvement.
2. Single-table control slice does not regress materially (tolerance < 1.0%).
3. Ablation shows gain is from relationship reasoning.
   - Phase 7B pass threshold: each ablation must lose >= 5 percentage points
     EX on its targeted slice versus the full `relationship_aware` system.
4. Phase 7C identifies the single largest root-cause bucket among incorrect
   cases (`missing_table`, `wrong_fk`, `missing_bridge`, `fanout_grain`,
   `sql_generation_despite_correct_plan`) so Phase 7D can target it directly
   instead of refactoring broadly.
   - Run with `chatsql analysis phase7c-error-analysis --run-dir <run>
     --output-dir <dir>` (add `--db-root <mini_dev db root>` to enable
     accurate `missing_bridge` detection via the relationship graph).
5. Phase 7D fixes only the single largest bottleneck identified above, then
   reruns and re-measures the affected slice to confirm the fix (not a broad
   refactor).
   - Gate with `chatsql analysis phase7d-slice-metrics --run-dir <run>
     --db-root <mini_dev db root> --output-dir <dir>` (per-slice reasoner
     quality, independent of LLM generation quality) and
     `chatsql analysis phase7d-hardening-gate --before-run <run>
     --after-run <run> --target-slice <slice> --db-root <mini_dev db root>
     --output-dir <dir>` (pass = target slice improves, no other slice
     regresses by more than 1pp).

## Execution Status (2026-09-05)

Phases 7A-7D's CLI/report machinery is implemented, wired end-to-end, and has
now been exercised against the **real** BIRD Mini-Dev SQLite data (500
questions, 11 databases, extracted from the official `minidev.zip` into
`third_party/mini_dev/llm/mini_dev_data/`) — not synthetic fixtures. Several
real bugs were found and fixed while doing this (see below).

**No OpenAI API key was available in this environment**, so a genuine
`gpt-4o-mini` run of all five systems (full_schema, relationship_aware, A1,
A2, A3) has **not** been executed, and gate criteria #1-#3 above (all
EX-based) remain **unverified** — this is a real gap, not a formality, since
the exit gate is defined on EX. `chatsql experiment run` with the checked-in
`configs/experiments/*.yaml` (provider: openai) is ready to produce that data
once a key is supplied; no code changes are needed to run it for real.

What **was** verified for real, without an LLM: the join-path/grain plan
built by `SemanticRelationshipReasoner` is deterministic and independent of
the LLM, so its quality against real gold SQL (edge recall, path coverage,
wrong-edge rate) is genuine signal today. Using a `provider: stub`
(deterministic, no-network) LLM client on the real 500-case benchmark:

- Found and fixed a real Phase 7D bottleneck: the reasoner treated every
  table the grounder retrieved (a fixed top-k + FK-neighbor closure,
  regardless of query complexity) as a mandatory join target, forcing bogus
  multi-table joins even on single-table gold queries (mean hop count 5.08 on
  the `single_table` slice before the fix). Fixed in
  `SemanticRelationshipReasoner._filter_relevant_tables`
  (`src/chatsql/relationships/reasoner.py`): candidate tables with zero
  lexical relevance to the question are dropped before path planning (a
  dropped table can still resurface as a genuine bridge hop). Verified via
  `phase7d-hardening-gate`: `single_table` quality score +0.10 with every
  other slice also improving, none regressing (report:
  `research/join_reasoning/phase7_execution_reports/phase7d_hardening_gate_report.md`).
- The A1/A3 ablations show directionally sensible real relationship-metric
  deltas (A1 no-role-disambiguation: edge recall 0.603 -> 0.560; A3
  no-bridge-expansion: path coverage 0.892 -> 0.842), consistent with the
  hypothesis that role disambiguation and bridge expansion each contribute
  real value independent of final SQL quality. A2 (no-grain-validation)
  showed ~zero relationship-metric movement on this sample, which is
  plausible — grain validation mainly affects prompt content and tie-breaks
  among equal-length paths, not table/edge selection, and is best tested on
  the `grain_sensitive_aggregation`/`fanout_aggregation` slices that Phase 6B
  never finished defining (see `ablations.md`).
- EX-based numbers from these stub runs are **not evidence either way** for
  gate criteria #1-#3: every system predicts the same placeholder SQL text,
  so EX is identical (3.0%) across all five systems by construction. Phase
  7C's bucketing on this stub run is similarly uninformative (dominated by
  `missing_table`, which is the placeholder-SQL artifact, not a real
  relationship-reasoning defect) — full Phase 7C bottleneck-finding still
  requires a real LLM run.

Other real bugs fixed while wiring this up (independent of the stub/no-key
limitation):
- `chatsql experiment run --dry-run` built a live OpenAI client (and failed
  without the `openai` package/key) before checking the dry-run flag,
  defeating its "validate wiring only" purpose. Reordered in `src/chatsql/cli.py`.
- The A1/A2/A3 ablation configs had no way to actually vary the reasoner —
  `RelationshipAwareStrategy` hardcoded default `SemanticRelationshipReasoner()`
  params. Added `reasoner_config` wiring through the CLI's `strategy.reasoner`
  YAML block (`configs/experiments/relationship_ablation_a{1,2,3}_*.yaml`).
- The fine-grained join slices (`1_hop_join`, `2_hop_join`, `3_plus_hop_join`,
  `multiple_fk_ambiguity`, `bridge_table_required`) that this document and
  `experiment_matrix.md` name were defined in `join_slices.py` but never
  actually attached to a run's slice summary — `analyze_run_directory` only
  ever produced the coarse `table_slice`/`join_depth` dimensions, so the 7A/7B
  gates were silently falling back to those. Added an opt-in
  `join_relationship` slice dimension (`chatsql analysis run --db-root ...`)
  computed from the real predicates.
- `relationship_benchmark_gate.py`'s single-table exclusion checked
  `join_depth == "single_table"`, a value that dimension never actually takes
  (`slice_case` emits `"0_joins"`), so the single-table baseline slice was
  incorrectly eligible to count toward the "join-heavy slice improved" gate
  criterion. Fixed to check `"0_joins"`.
