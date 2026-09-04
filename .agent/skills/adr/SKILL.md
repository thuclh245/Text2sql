---
name: adr
description: >-
  Create a CHATSQL Architecture Decision Record with the next sequential number.
  Use when the user says "viết ADR", "record this decision", "we decided to...", or
  makes a choice that is expensive to reverse (canonical metadata representation,
  benchmark policy, process/container isolation, semantic IR, authorization
  placement, model-provider abstraction). Follows docs/12_ENGINEERING_STANDARDS.md §6
  and docs/templates/ADR_TEMPLATE.md.
---

# Skill: create a CHATSQL ADR

## When to use

A decision that is expensive to reverse (doc 12 §6 list). Do NOT use ADRs for
trivial implementation details — those go in code review or a task brief.

## Steps

1. **Get the next number.** List `docs/adrs/`, find the highest `ADR-XXXX`, add 1,
   zero-pad to 4 digits.

2. **Fill `docs/templates/ADR_TEMPLATE.md`.** Every heading:
   - `Status` — usually `Proposed` on creation.
   - `Context` — the forces and constraints.
   - `Evidence` — classify on the doc 04 §2 hierarchy; link
     `docs/16_SOURCES_AND_EVIDENCE.md` entries where relevant.
   - `Decision` — the choice, stated imperatively.
   - `Alternatives considered` — at least the realistic ones, with why-not.
   - `Consequences` — including what becomes harder.
   - `Research impact` — does this change experimental behavior? If yes, note which
     experiment IDs are affected and that comparability may break.
   - `Revisit trigger` — the concrete evidence that would reopen this ADR.

3. **Write** to `docs/adrs/ADR-XXXX-<kebab-title>.md`.

4. If it supersedes an earlier ADR, set that one's `Status` to `Superseded` with a
   pointer to the new number.

## Guardrails

- Keep the number stable once assigned.
- If the decision changes research behavior, the corresponding experiments need new
  IDs (doc 15 §5) — say so in the ADR and to the user.
