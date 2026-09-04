---
name: hypothesis
description: >-
  Draft a falsifiable CHATSQL research hypothesis and check it against the gate
  sequence. Use when the user says "viết hypothesis", "new research idea", "propose
  a contribution", "H#", or before starting any E6 contribution experiment. Enforces
  docs/04_RESEARCH_METHOD.md §1-§3 and docs/templates/HYPOTHESIS_TEMPLATE.md.
---

# Skill: draft a CHATSQL hypothesis

## When to use

The user has a research idea. Per doc 04 §1, an idea may not jump straight to
implementation — it must pass: Observation → Failure evidence → Literature check →
Falsifiable hypothesis → Strong baseline → Controlled experiment → Ablation → Error
analysis → Cross-setting validation → Claim/reject.

## Steps

1. **Demand failure evidence.** Ask for / locate the experiment IDs and case counts
   showing the failure this idea targets. No measured failure share → the idea is
   premature; say so (doc 18 v0.4 requires an error budget identifying a real
   bottleneck).

2. **Do the literature check.** Consult `docs/16_SOURCES_AND_EVIDENCE.md` and the
   relevant research doc (07 grounding, 08 relationship/join, 09 semantic model).
   Classify supporting evidence on the doc 04 §2 hierarchy (1 peer-reviewed w/
   artifact … 6 engineering intuition). If only levels 5–6, label tentative.

3. **Fill `docs/templates/HYPOTHESIS_TEMPLATE.md`.** Every heading. The `Hypothesis`
   line must be ONE falsifiable sentence in the doc 04 §3 style: name the target
   failure subset, the changed component, the unchanged components, the primary
   metric, expected direction. Reject vague forms like "semantic context will
   improve CHATSQL".

4. **Specify explicitly**: target failure subset, changed component, fixed
   components, dataset/subset, primary metric, secondary metrics, expected
   mechanism, and the failure criterion (what result rejects it). Also ablations,
   risks/confounders.

5. **Name the baseline discipline** (doc 04 §4): which is the modernized baseline C
   that the contribution D must beat — not just the old published score A.

6. **Write the file** to `research/hypotheses/<H-id>.md` and leave the decision
   checkboxes unchecked. Note that no M5 implementation starts before an approved
   hypothesis artifact exists (doc 17 T44).

## Guardrails

- One falsifiable sentence, or it is not a hypothesis.
- Do not let a hypothesis skip the strong-baseline or error-analysis gates.
