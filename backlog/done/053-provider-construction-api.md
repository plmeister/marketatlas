# 053: Provider Construction API — EMA(period=20)

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

A declarative Python construction API that mirrors YAML semantics and is the future target of the YAML parser:

```python
EMA(period=20)
EMA(period=Choice([50, 100]))
```

Each call returns a `Definition` (or definition fragment) referencing the resolved provider, with non-Expression kwargs wrapped in `LiteralExpression` (backlog 047). The API resolves capability → provider via the default registry, applies default params, and validates parameter names/types at construction time (reusing backlog 052 metadata). This is the intermediate representation the DSL parser (057) targets — the DSL constructs the same nodes this API produces.

## Scope

- New module `src/marketatlas/analysis/ast/constructors.py` with factory functions for the built-in providers (ema, atr, trend, swingstructure, swings, sr, detect_pullback, generate_signal, manage_risk)
- `Choice` exposed for `ChoiceExpression` construction
- Composition: defs combine into an `Analysis` (drop-in with `AnalysisBuilder`/compiler)
- Construction-time errors mirror 052 validation (unknown kwarg, missing required, wrong type)

## Non-Goals

- No DSL parser (backlog 057) — this API is its construction target
- No graph construction — the API produces AST only

## Acceptance Criteria

- [ ] `EMA(period=20)` → Definition with provider `ema`, literal param `period=20`
- [ ] `EMA(period=Choice([50, 100]))` → Definition with `ChoiceExpression` param
- [ ] Registry resolution + default-param application at construction; explicit kwargs override defaults
- [ ] Unknown kwarg raises immediately with provider name; missing required param raises; wrong type raises (per 052)
- [ ] `Choice` accepts literal/expression members and wraps literals
- [ ] Literal-only definitions compile via existing `ASTCompiler.compile` (single-graph path)
- [ ] Tests: constructor outputs, error paths, composition into `Analysis`

## Related

- Backlog 047 (literal wrap), 048 (`Choice`), 052 (param validation), 040 (compiler adapter)
- Backlog 057: DSL parser targets this API (or constructs the AST directly)
