---
name: task
description: >-
  Draft a spec-complete CHATSQL task brief to hand to a coding agent. Use when the
  user says "create a task", "viết task", "giao việc cho agent", "chuẩn bị task cho
  <T##>", or wants to decompose work from docs/17_IMPLEMENTATION_BACKLOG.md. Produces
  a filled docs/templates/TASK_TEMPLATE.md that satisfies the agent workflow rules in
  docs/15_AGENT_WORKFLOW.md.
---

# Skill: draft a CHATSQL task brief

## When to use

The user wants to give a coding agent (or a future session) a unit of work. Every
task in this repo must use `docs/templates/TASK_TEMPLATE.md` and satisfy
`docs/15_AGENT_WORKFLOW.md §2`.

## Steps

1. **Locate the source of the task.**
   - If the user references a backlog ID (e.g. `T11`), read that entry in
     `docs/17_IMPLEMENTATION_BACKLOG.md` and carry its Output/Acceptance verbatim
     into the brief.
   - Otherwise derive Goal/Acceptance from the user's request. If the request is
     broad ("improve accuracy", "cải thiện retrieval"), STOP and split it — per
     doc 15 §6 a good task is one component (e.g. "implement `BirdBenchmarkProvider`",
     "add unit tests for `InferenceCase`"), not an outcome.

2. **Fill every section of the template.** Do not leave a heading empty.
   - `Goal` — one sentence, one component.
   - `Inputs` — configs, fixtures, upstream code, docs the agent needs.
   - `Files allowed to change` — explicit paths. Respect ownership rules in
     `docs/03_REPOSITORY_STRUCTURE.md §2` (`src/chatsql/` = CHATSQL-owned only;
     `third_party/` never gets contribution code; upstream changes go in
     `patches/` with a rationale record).
   - `Files forbidden to change` — always list: benchmark gold data, pinned
     baselines under `third_party/`, official evaluators, experiment configs whose
     ID would change silently. Add task-specific ones.
   - `Acceptance tests` — concrete commands (`pytest tests/unit/test_xxx.py`,
     `chatsql experiment run ... --limit 10`) and observable pass criteria. A smoke
     test is not a research result (doc 15 §4).
   - `Research behavior impact` — check the box. It is behavior-changing if it
     touches prompt, model, retriever, semantic representation, relationship
     scoring, correction loop, context policy, or evaluator (doc 15 §5). If so, the
     task MUST also create a new config / experiment ID and must not overwrite
     previous results.
   - `Evidence / references` — cite docs sections or `docs/16_SOURCES_AND_EVIDENCE.md`
     entries when the task encodes a research assumption.

3. **Apply the naming policy** (doc 12 §8): scientific-role names
   (`full_schema_control`, `lite_sql_reproduced`, `chatsql_grounder_v1`), never
   `best`, `final`, `new2`.
   For files, configs, run IDs, benchmark IDs, test fixtures, and public
   parameters, use names that describe the domain role or controlled variable
   (`bird_mini_dev_sqlite_select_500`, `foundation_dummy_run`,
   `full_schema_control`). Do not name runtime artifacts after roadmap labels
   like `phase`, `P0`, `P1`, `task`, or `step`; those labels may appear only when
   quoting source docs/backlog text.

4. **Write the file** to `docs/tasks/<ID-or-slug>.md` (create `docs/tasks/` if
   needed). Keep the template's "Completion report format" block so the agent knows
   how to close out — see the `task-report` skill.

5. **Tell the user** the path and the one-line summary of scope + whether it is
   behavior-changing.

## Guardrails

- Never widen "Files allowed to change" to whole directories when a few files
  suffice.
- If acceptance can't be made concrete, say so and ask the user rather than
  shipping a vague task.
- Before handing off, scan newly introduced paths, identifiers, config keys, and
  test names for vague roadmap labels (`phase`, `P0`, `P1`, `final`, `new2`) and
  rename them to scientific-role names.
