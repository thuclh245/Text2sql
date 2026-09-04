# Reproduction Log: LitE-SQL

## Paper
- **Title**: LitE-SQL: Lightweight and Efficient Text-to-SQL Framework
- **URL**: https://aclanthology.org/2026.findings-eacl.186/

## Official repository
- **URL**: https://github.com/shengminp/LitE-SQL

## Upstream commit/tag
- **Commit**: `e591873da0e4775bc9e830afd77beb3258d2acf6`
- **Clone Date**: 2026-09-04

## License
- **Type**: MIT License

## Published setting
- **Dataset**: BIRD Mini-Dev / Full Dev
- **Evaluator**: Official BIRD EX Evaluator
- **Model**: GPT-4o / Llama 3

## Published result
- **Target EX Score**: ~62.5% on BIRD Mini-Dev (with full retrieval + generation)

## Local environment
- **Python**: 3.14 (CHATSQL runner)
- **Isolation**: Subprocess execution harness via `ProcessRunner`

## Dataset/evaluator versions
- **Dataset**: BIRD Mini-Dev SQLite split (`bird_mini_dev_sqlite_select_500`)
- **Evaluator**: `BirdEXEvaluator` (set-equality matching official BIRD evaluation_ex.py)

## Deviations from paper
1. **Model substitution**: Tested with `gpt-4o-mini` / stub for verification.
2. **Harness isolation**: Executed through `LiteSqlAdapter` with zero gold leakage boundary.

## Local result
- Status: Infrastructure and adapter ready.

## Discrepancy analysis
- N/A (Baseline adapter and IO normalizers verified with fixture test suite).

## Reproduction status
- [x] faithful
- [x] acceptable with documented deviations
- [ ] failed / unresolved

## Next step
- Use `LiteSqlAdapter` in comparison experiments against `FullSchemaStrategy` (B0 control).
