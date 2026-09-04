---
name: reproduction-log
description: >-
  Scaffold a CHATSQL reproduction log for a published baseline (LitE-SQL, DIN-SQL,
  CHESS, ATR, ...). Use when the user says "reproduce <system>", "viết reproduction
  log", "pin the upstream baseline", or is working through M2 backlog tasks
  (T21-T26). Follows docs/05_BASELINE_REPRODUCTION.md, docs/04_RESEARCH_METHOD.md §4,
  and docs/templates/REPRODUCTION_LOG_TEMPLATE.md.
---

# Skill: scaffold a reproduction log

## When to use

Reusing a published Text-to-SQL system as a baseline. Reproduction must be
traceable: the goal is `published upstream (A) → local reproduced (B)`, with every
deviation documented (doc 04 §4).

## Steps

1. **Register upstream metadata** (doc 17 T21): paper URL, official repo URL,
   license, exact commit/tag, and the published result + published setting. Record
   these into `docs/16_SOURCES_AND_EVIDENCE.md` if not already there.

2. **Environment isolation** (doc 12 §1): the baseline gets its own Conda/Docker
   env, NOT the CHATSQL core env. Prefer the upstream's own environment first.
   Upstream code lives pinned under `third_party/<System>/`; compatibility changes
   go in `patches/<system>/` with rationale (why, does it change algorithmic
   behavior, expected output impact, author/date — doc 03 §2).

3. **Fill `docs/templates/REPRODUCTION_LOG_TEMPLATE.md`.** Every heading. Be
   explicit in:
   - `Deviations from paper` — model, checkpoint, dataset revision, evaluator,
     hardware, dependencies. List each one.
   - `Discrepancy analysis` — `B - A` interpreted as reproduction discrepancy, not
     a research finding.
   - `Reproduction status` — check faithful / acceptable-with-deviations / failed.

4. **Small smoke first** (T23): run upstream on a few BIRD cases before writing any
   adapter. Only then normalize output into CHATSQL `StrategyResult` via
   `baselines/<system>.py` without altering upstream behavior (T26).

5. **Write** the log to `research/reports/reproduction-<system>.md`.

## Guardrails

- Any modernization (new model, updated deps that change behavior) is a SEPARATE
  named baseline (C), not folded into the reproduction (B) — doc 18 v0.2.
- B0 and a reproduced baseline are comparable only where settings actually match.
- Do not rely on a mutable remote `main` for the dataset or upstream code (doc 12
  §7) — pin everything.
- Name reproduction artifacts by system, benchmark, and role
  (`lite_sql_reproduced_bird_mini_dev`, `chess_original_spider`) rather than
  roadmap labels such as `phase`, `P2`, or `task`.
