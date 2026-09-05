# AGENTS.md

Instructions for any coding agent (Codex, Claude Code, Gemini Antigravity, etc.)
working in this repository.

## Naming Conventions

Names are read far more often than they are written. Pick the name that lets
someone understand what a thing *is* or *does* without opening its definition.

- **Files/modules** — `snake_case`, one concern per file. The filename names
  what it exports: `grounding/schema_linker.py` exports `SchemaLinker`, not
  `grounding/utils2.py`.
- **Tests** — mirror the module under test:
  `src/chatsql/<area>/<module>.py` → `tests/unit/test_<module>.py`
  (see `tests/unit/test_domain.py`, `test_relationship_graph.py`, etc.).
  Test functions read as a sentence:
  `test_<unit>_<condition>_<expected_outcome>`, e.g.
  `test_link_columns_missing_table_raises_value_error`. Avoid
  `test_1`, `test_case_a`, `test_it_works`.
- **Functions** — `verb_noun`, snake_case: `compute_relationship_graph`,
  `link_schema_columns`. Avoid vague verbs (`handle_`, `process_`, `do_`,
  `manage_`) that don't say what happens.
- **Classes** — `PascalCase` noun phrases naming the concept itself:
  `SchemaLinker`, `RelationshipGraph`. Avoid generic suffixes that describe no
  behavior (`Manager`, `Helper`, `Util`, `Base` unless it's genuinely an
  abstract base).
- **Booleans** — prefix with `is_`, `has_`, `should_`, `can_`:
  `is_valid`, `has_foreign_key`, not `valid_flag`.
- **Constants** — `UPPER_SNAKE_CASE`, defined once near top of module or in
  `config/`.
- **Abbreviations** — only domain-standard ones stay short: `sql`, `db`, `id`,
  `cfg` (if already used consistently in this codebase). Don't invent new
  abbreviations (`tmp`, `mgr`, `proc`) — spell it out.
- **No versioning/history in names** — no `new_`, `old_`, `v2_`, `final_`,
  `_fixed`. Git history is where "what changed" lives, not the identifier.
  Rename in place instead of adding a suffix.
- **Single-letter names** — only for loop indices (`i`, `j`) or short lambda
  args. Everything else gets a real name, including short-lived locals.

When renaming or introducing a name, prefer clarity over brevity: a longer,
unambiguous name (`relationship_graph_builder`) beats a short, ambiguous one
(`rg_builder`).
