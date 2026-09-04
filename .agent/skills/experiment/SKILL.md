---
name: experiment
description: >-
  Scaffold a controlled CHATSQL experiment: the experiment doc, the frozen manifest,
  and the result-directory contract. Use when the user says "tạo experiment", "set up
  E#", "run a controlled comparison", "new ablation", or wants to compare systems/
  retrievers/models. Enforces docs/06_EXPERIMENT_PROTOCOL.md and
  docs/04_RESEARCH_METHOD.md §4-§6.
---

# Skill: scaffold a CHATSQL experiment

## When to use

The user wants to run or design an experiment (E0–E6, or an ablation). A result is
only interpretable if exactly one variable changed and no gold data leaked.

## Steps

1. **Identify the experiment family** from `docs/06_EXPERIMENT_PROTOCOL.md §4`
   (E0 harness validation, E1 B0 full schema, E2 reproduce LitE-SQL, E3 retrieval
   comparison, E4 relationship oracle, E5 oracle semantic model, E6 CHATSQL
   contribution). E6 requires an approved hypothesis first — see the `hypothesis`
   skill. If none fits, ask.

2. **Fill `docs/templates/EXPERIMENT_TEMPLATE.md`.** Every heading. Be explicit
   about:
   - `Systems compared` — name them with the A/B/C/D baseline discipline of doc 04
     §4 (published upstream / local reproduced / modernized / modernized + CHATSQL).
   - `Controlled variables` vs `Changed variable` — from doc 04 §5 fix benchmark
     split+version, DB files, evidence availability, SQL generator, model/checkpoint,
     temperature/sampling, prompt version, executor, correction budget, evaluator,
     seed. Exactly one moves. Any variable that can't be fixed is recorded and
     discussed, not ignored.

3. **Write the frozen manifest** (`docs/06 §3` YAML shape) into the experiment's
   config under `configs/experiments/<experiment_id>.yaml`: experiment_id,
   benchmark{name,version,split,dataset_hash,evaluator_hash}, system{name,
   upstream_commit,patch_hash}, model{provider,id,checkpoint,temperature,seed},
   context{evidence_mode,metadata_budget}, retrieval{strategy,hyperparameters},
   execution{dialect,read_only,timeout_seconds}, correction{enabled,budget}.
   Use a scientific-role `experiment_id` (doc 12 §8), never `best`/`final`.
   The ID must describe the benchmark/system/change being tested, not the
   roadmap position. Good: `bird_mini_dev_sqlite_full_schema_control`,
   `lite_sql_reproduced_bird_mini_dev`, `fk_closure_retrieval_ablation`.
   Bad for runtime artifacts: `phase_1`, `p1_run`, `task_35`, `new_test`.

4. **State the result-directory contract** the run must emit (doc 04 §6):
   `config.yaml`, `manifest.json`, `predictions.jsonl`, `metrics.json`,
   `errors.jsonl`, `environment.json`, `README.md` under `runs/<experiment_id>/...`.
   `environment.json` records git commit, dirty flag, OS, Python, CUDA/driver,
   dependency lock hash, model/checkpoint, dataset hash, evaluator hash, seed.

5. **Leakage guard** (doc 06 §2): inference sees only question, db id,
   benchmark-permitted evidence, policy-allowed metadata. Gold SQL/tables/columns/
   result are evaluation-only. Confirm `tests/leakage/` covers this path.

6. **Pick metrics** from doc 06 §6 (EX via official evaluator + R-VES/Soft F1 when
   using official BIRD Mini-Dev; retrieval recall/FPR; relationship path metrics;
   system cost). Name a primary and secondaries.

7. **Write the experiment doc** to `research/hypotheses/` or `research/reports/` as
   appropriate; link the config path. If the experiment claims an improvement,
   remind the user of the 7-point acceptance rule (doc 06 §7).

## Guardrails

- Never let gold fields into an inference request or config.
- Do not overwrite an existing `experiment_id`'s runs — new behavior = new ID.
- Negative results are kept (doc 04 §7): if it fails, record hypothesis, config,
  result, why, and whether to revisit.
- Roadmap labels such as `E3`, `P1`, or `T35` can be cited in prose, but they
  must not be the primary name for configs, runs, benchmark identifiers, public
  parameters, or result directories.
