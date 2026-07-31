# 052: Provider Metadata Validation — Params and Types

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

Validate parameter usage against provider metadata: the provider exists, parameter names are known, required parameters are present, and expression/literal values are type-compatible with what the provider expects. Explicitly NOT graph-level checks (binding targets, cycles — already covered by `validate` in validation.py:77).

Today the registry (registry.py) only stores `default_params`; there is no schema describing allowed/required parameter names or types. Provider existence is checked against AST-declared providers in validation.py:110, but nothing validates params against the resolved provider.

## Scope

- Extend `Provider` (models.py) or the registry with a parameter schema: names, required vs optional (derive required from missing default), expected types
- Registry derives the schema automatically from analyzer constructors for the built-in providers (introspect `__init__` signatures/defaults) with manual override where signatures are opaque
- New validation pass (or extension of stage-1 validation) running against resolved providers:
  - unknown parameter name → error
  - missing required parameter → error
  - literal/expression value type incompatible with expected → error (evaluated pre-expansion; a `ChoiceExpression` is type-checked per leaf)
- Runs post-registry-resolution, pre-expansion (per backlog 051 stage ordering)

## Non-Goals

- No graph/dependency validation (bindings, cycles) — stays in existing `validate()`
- No range/value constraints (e.g. `period > 0`) unless trivially cheap — defer to future work

## Acceptance Criteria

- [ ] `Provider` carries a param schema (names, required, expected types)
- [ ] Built-in providers expose correct schemas derived from constructors (spot-check `ema.period`, `atr.period`, swing `lookback`, `sr`, risk)
- [ ] Validation errors: unknown param name, missing required param, wrong type — each with definition + parameter name
- [ ] `ChoiceExpression` leaves type-checked individually (e.g. `Choice([20, "x"])` on an int param errors on the string leaf)
- [ ] Graph deps unaffected: existing cycle/binding validation tests unchanged
- [ ] Tests: table-driven cases per provider + expression-type edge cases

## Technical Notes

- Type checks are best-effort for analyzer signatures (params often `int`/`float`/`str`); treat union/`Any` as accept-all rather than false-positiving.
- Prefer registry-held schema keyed by provider name to keep `models.py` stable; decide during build.

## Related

- Backlog 047/048 (expression types), 051 (stage ordering), 053 (construction API reuses schema)
- `src/marketatlas/analysis/ast/registry.py`, `validation.py`, `pipeline.py`
