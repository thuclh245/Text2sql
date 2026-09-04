---
name: task-report
description: >-
  Close out a CHATSQL coding task: produce the mandatory 7-point completion report
  and run the agent safety checklist before declaring done. Use when a task's code
  changes are finished, when the user says "viết completion report", "kết thúc task",
  "wrap up", or asks whether the change is safe to merge. Enforces
  docs/15_AGENT_WORKFLOW.md §3-§5 and docs/18_DEFINITION_OF_DONE.md.
---

# Skill: CHATSQL task completion report

## When to use

Code changes for a task are done and you need to report them in the format doc 15
§3 requires, having verified doc 15 §4 safety rules.

## Steps

1. **Gather the diff.** `git diff` / `git status` for the actual changed files and
   `git log` for context. Do not report from memory.

2. **Run the safety checklist** (doc 15 §4). Confirm the change did NOT:
   - modify pinned third-party baselines without a patch record in `patches/`
   - change benchmark gold data
   - replace an official evaluator silently
   - expose `GoldCase` to inference/strategy code (check `tests/leakage/` still
     passes)
   - change model / prompt / retrieval hyperparameters inside an existing
     experiment without a new config / experiment ID
   - claim an accuracy improvement without running the defined evaluator
   - present a smoke test as a research result

   If any is violated, do NOT write a "done" report — surface the violation and
   the fix needed.

3. **Classify research-behavior impact** (doc 15 §5). Behavior-changing if it
   touched: prompt, model, retriever, semantic representation, relationship
   scoring, correction loop, context policy, or evaluator. If yes, verify a new
   experiment config / ID exists and old runs are not overwritten.

4. **Run the acceptance tests** from the task brief and record real output
   (command + pass/fail). If a test was skipped, say so explicitly.

5. **Check naming hygiene.** New or changed files, configs, run IDs, benchmark
   IDs, test fixtures, and public parameters should use scientific-role names.
   Do not approve names based mainly on roadmap labels such as `phase`, `P0`,
   `P1`, `task`, `final`, or `new2`, except when quoting source docs/backlog
   labels in prose.

6. **Check runtime wiring.** If the task added a public CLI option, config key,
   strategy, executor, evaluator, or logger artifact, verify one test or smoke
   command exercises the real path. Do not approve a completion report while the
   main run path still contains a placeholder stub or while a checked-in config
   names identifiers the CLI cannot resolve.

7. **Write the report** in exactly this shape (doc 15 §3):
   ```
   1. What changed
   2. Why it changed
   3. Files changed
   4. Tests run and result
   5. Research behavior changed? yes/no
   6. Known limitations
   7. Next recommended step
   ```
   Explain each technical term in a short parenthetical on first use.

8. **Check the relevant DoD gate** in `docs/18_DEFINITION_OF_DONE.md` (v0.1–v1.0)
   and state which gate criteria this task advances or completes.

9. If a PR is expected, offer to write it — body ends with the required
   attribution line.

## Guardrails

- State test failures plainly with the output. Never round a partial result up to
  "done".
- If research behavior changed, the report's item 5 is "yes" even if the metric
  moved favorably.
