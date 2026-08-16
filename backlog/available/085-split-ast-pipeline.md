# 085: Split analysis/ast/pipeline.py into smaller modules

**Status:** pending
**Epic:** ast
**Priority:** medium
**Depends on:** none

## Description

`analysis/ast/pipeline.py` is 939 lines — the largest file in the codebase.
It handles DSL expansion, IR lowering, fact-key compilation, and strategy
orchestration in a single module. An agent editing expansion rules must load
the entire file including unrelated lowering logic.

Split into three single-responsibility modules:

- **`ast/expansion.py`** (~400 lines) — the expansion rule engine: pattern
  matching on DSL definitions, macro expansion, choice-variant generation.
  Pure transformation, no compilation.
- **`ast/lowering.py`** (~350 lines) — IR lowering and fact-key compilation:
  `_resolve_reference`, `_check_fact_declared`, `_compile_strategy` core
  logic, reference→key mapping, bindings injection.
- **`ast/pipeline.py`** (~150 lines) — thin orchestrator: `expand()`,
  `compile()`, `lower()` entry points that compose the above. Public API
  unchanged.

## Design

1. `expansion.py` exports `expand(analysis: Analysis) -> Analysis` — takes a
   parsed AST, applies all expansion rules (choices, groups, implicit refs),
   returns expanded AST. No imports from `lowering.py`.
2. `lowering.py` exports `compile_strategy(analysis, registry) -> Compilation`
   and `resolve_references(analysis, registry) -> dict`. Imports from
   `expansion.py` only to call `expand()` internally if needed.
3. `pipeline.py` re-exports the public API so all existing callers
   (`cli.py`, `instrument.py`, `compiler.py`, `loader.py`) continue to
   `from marketatlas.analysis.ast.pipeline import expand, compile`.
4. Internal helpers (`_expand_choice`, `_expand_group`, `_collect_definitions`)
   move to `expansion.py`; `_resolve_reference`, `_check_fact_declared`,
   `_derive_bindings` move to `lowering.py`.
5. Circular imports avoided: `lowering.py` imports `expansion.py` (one-way).

## Acceptance Criteria

- [ ] `pipeline.py` <200 lines, `expansion.py` <450 lines, `lowering.py` <400 lines
- [ ] All existing imports from `pipeline.py` still resolve (re-exports)
- [ ] No circular imports (checked by `python -c "from marketatlas.analysis.ast.pipeline import expand"`)
- [ ] `pytest tests/test_ast_pipeline.py tests/test_ast_golden_expansion.py tests/test_ast_expand.py tests/test_ast_validation.py` — all pass
- [ ] `ruff check` clean, `mypy` clean
- [ ] No new public API — only internal reorganization

## Related

- `src/marketatlas/analysis/ast/pipeline.py` (939 lines, primary target)
- `src/marketatlas/analysis/ast/registry.py` — consumed by lowering
- `src/marketatlas/cli.py` — imports from pipeline
- `src/marketatlas/analysis/ast/instrument.py` — imports from pipeline
