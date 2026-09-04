# CHATSQL project skills

Project-scoped Claude Code skills that package the workflow rules in `docs/` into
tools. Invoke with `/task`, `/experiment`, etc., or let Claude trigger them.

| Skill | Purpose | Governing docs |
|---|---|---|
| `task` | Draft a spec-complete task brief for a coding agent | 15, 17, 03, 12 |
| `task-report` | 7-point completion report + agent safety checklist | 15, 18 |
| `experiment` | Scaffold a controlled experiment + frozen manifest | 06, 04 |
| `hypothesis` | Draft a falsifiable hypothesis, check the gate sequence | 04, 07-09 |
| `adr` | Create an ADR with the next sequential number | 12 |
| `reproduction-log` | Scaffold a baseline reproduction log | 05, 04 |

Each skill reads the relevant template under `docs/templates/` and fills it.
