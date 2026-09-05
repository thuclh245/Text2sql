# Phase 6B Research Hypothesis Summary

Refer to full hypothesis document: [H02_relationship_path_reasoning.md](../hypotheses/H02_relationship_path_reasoning.md)

## Core Statement
Explicit multi-hop relationship path planning, foreign-key role disambiguation, and query entity grain validation in prompt context will increase Execution Accuracy (EX) on multi-table join queries in BIRD Mini-Dev SQLite by at least 2.5 percentage points compared to the modernized full-schema baseline without decreasing accuracy on single-table queries.

## Failure Criteria
Reject hypothesis if multi-table join EX does not improve by at least 1.0 percentage points, or if single-table query EX regresses by more than 1.0 percentage points.
