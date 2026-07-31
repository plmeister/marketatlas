# 048: ChoiceExpression Node

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Add `ChoiceExpression` to the expression hierarchy (backlog 047). Represents "one of a finite set of candidate values" for a parameter — the AST-level primitive that will later drive template expansion. A choice must be explicit: a Python `list` passed as a param value stays a plain literal (a list-valued param), never implicitly a choice.

## Scope

- `ChoiceExpression(values: tuple[Expression, ...])` in `expressions.py`
- Structured JSON serialization, distinct from raw literal values
- Builder: `with_param("period", Choice([50, 100]))` accepts `Expression` objects as-is
- Defensive error in `_ast_to_config` when a choice reaches config generation (no expansion yet): `CompilationError` naming the definition and parameter

## Non-Goals

- No expansion logic (backlog 050)
- No cartesian product handling here

## Acceptance Criteria

- [ ] `ChoiceExpression` constructible with any number of Expression leaves, including nested `ChoiceExpression` (nested choices allowed at node level)
- [ ] Equality/repr; empty choice constructible at node level (error deferred to validation/expansion — see 054)
- [ ] Serialization round-trip: structured `{"expr": "choice", "values": [...]}` distinguishable from a raw list literal `[50, 100]`
- [ ] Builder accepts Expression params; a list literal param still serializes as a raw list (not a choice)
- [ ] Compiling an AST containing an unexpanded choice raises `CompilationError` with definition + parameter name
- [ ] Tests: node semantics, serialization, literal-vs-choice distinction, defensive compile error

## Related

- Backlog 047: expression hierarchy (prereq)
- Backlog 050: template expansion consumes this
- Backlog 054: choice behaviour spec tests
- `src/marketatlas/analysis/ast/expressions.py` (new), `serialization.py`, `pipeline.py`
