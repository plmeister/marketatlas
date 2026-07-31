# 050: Template Expansion Pass — ChoiceExpression → Concrete ASTs

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Template expansion converts an AST containing `ChoiceExpression` params into a set of concrete ASTs where every parameter is a literal. If a definition has `period=Choice([50, 100])`, expansion produces two variants. Multiple choices — across params or across definitions — combine by cartesian product. The output contains no `ChoiceExpression` nodes (guaranteed, asserted in tests).

## Scope

- New pass/function `expand(analysis) -> tuple[Analysis, ...]` in the pipeline module
- For each definition, for each `ChoiceExpression` param: expand
- Multiple choices in one definition → product; choices in different definitions → product across definitions
- Nested `ChoiceExpression` leaves → flattened into the product
- `list` literal param values are NOT choices (per backlog 048) and pass through untouched
- Empty choice → `CompilationError` (reported, not silently dropped)
- Dedup of identical concrete ASTs produced by convergent expansion — decide with 051/054: dedup here or report duplicates in stage-3 validation; document whichever is chosen

## Non-Goals

- No pipeline wiring (backlog 051) — the pass exposes `expand()` for direct testing
- No param-name/type validation (backlog 052)
- No graph generation

## Acceptance Criteria

- [ ] `expand` returns one concrete AST per cartesian combination; all params literal
- [ ] Single choice (EMA period 50/100) → exactly 2 ASTs
- [ ] Nested choice `Choice([Choice([1, 2]), 3])` → correct flattened products
- [ ] Two independent choices (EMA period × ATR period) → 2×2 = 4 ASTs
- [ ] List literal param `[50, 100]` stays a single AST with list value — never expands
- [ ] Empty choice raises `CompilationError` with definition + parameter
- [ ] Output guarantee: no AST in output contains a `ChoiceExpression`
- [ ] Idempotence: expanding a concrete AST returns a single equal AST
- [ ] Tests operate purely on ASTs (no registry/graph)

## Technical Notes

- Build each variant from the template using backlog 049 clone; never mutate the input AST.
- Product ordering must be deterministic and documented (choices iterate in declaration order, definitions preserve order) — 054 golden tests depend on it.
- Expansion count can explode (n choices → product); document in the docstring, no size guard needed yet.

## Related

- Backlog 047, 048 (prereq), 049 (clone), 051 (pipeline), 054 (golden tests)
