# 047: Expression Hierarchy for Parameter Values

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Introduce a typed expression hierarchy for parameter values, replacing `Parameter.value: Any` (models.py:19). Today every parameter value is an opaque Python object passed straight into `AnalyzerConfig.params` via `_ast_to_config` (pipeline.py:214). A value must be representable as a tree node so it can be validated, cloned, expanded, and serialized structurally — the foundation for template/choice parameters.

`Parameter.value` becomes an `Expression`. `LiteralExpression` wraps a concrete value and is the only node type until backlog 048 lands.

## Scope

- New module `src/marketatlas/analysis/ast/expressions.py`: `Expression` base + `LiteralExpression(value)`
- `Parameter.value: Expression` in `models.py`
- Builder (`builder.py:14`) and registry default-param paths (`registry.py:38,52,66`) wrap raw values in `LiteralExpression` — builder keeps accepting plain values, so existing tests constructors stay unchanged
- `_ast_to_config` unwraps `LiteralExpression.value` before building configs
- Serialization: a `LiteralExpression` serializes as its raw JSON value (keeps current format — existing round-trip tests and 046 snapshots stay green); only non-literal nodes get structured serialization (backlog 048)

## Non-Goals

- No choice/template semantics (backlog 048)
- No expansion (backlog 050)
- No behaviour change to the YAML config path

## Acceptance Criteria

- [ ] `LiteralExpression` exists with `value` attribute; sane equality and repr
- [ ] `Parameter.value` typed as `Expression`; all AST code compiles and existing tests pass (builder, registry, serialization, pipeline, compiler)
- [ ] Builder and registry accept raw values and wrap implicitly; existing test constructor calls unchanged
- [ ] `to_json`/`from_json` round-trip unchanged for literal-only ASTs (existing 33 serialization tests pass unmodified)
- [ ] Compiled graphs for existing analyses identical to pre-change (046 snapshots unchanged)
- [ ] `_ast_to_config` raises clear error on a non-literal expression (defensive; real handling in 048/050)

## Technical Notes

- Literal serialization must stay format-compatible: emit raw `{"name": ..., "value": 20}`, not `{"value": {"expr": "literal", ...}}`. Only version the format if unavoidable.
- `serialization._parameter_to_dict` / `_dict_to_parameter` are the round-trip contract — touch first.
- Consider an `unwrap(value) -> object` helper used by both config generation and tests.

## Related

- Backlog 048: ChoiceExpression node
- Backlog 050: template expansion
- Backlog 053: provider construction API
- `src/marketatlas/analysis/ast/models.py`, `builder.py`, `serialization.py`, `pipeline.py`
