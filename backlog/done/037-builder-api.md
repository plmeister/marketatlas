# 037: Builder API — Fluent AST Construction

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Fluent Python API for constructing the AST. Primary way to author analyses before a text DSL exists.

## Acceptance Criteria

- [ ] `AnalysisBuilder` class with chainable methods
- [ ] `define(name, type, impl)` registers a new definition node
- [ ] `with_param(name, value)` adds parameter to last definition
- [ ] `bind(source, output, target, input)` wires a binding
- [ ] `build()` produces immutable `Analysis` AST
- [ ] Multiple definitions supported
- [ ] Bindings reference definitions by name
- [ ] Builder validates at construction time (not build time)

## Usage Sketch

```python
analysis = (
    AnalysisBuilder("pullback_4swing", "1.0.0")
    .define("ema20", "analyzer", "EMAAnalyzer")
        .with_param("period", 20)
        .with_param("source", "close")
    .define("atr14", "analyzer", "ATRAnalyzer")
        .with_param("period", 14)
    .define("swing", "analyzer", "SwingStructureAnalyzer")
        .with_param("lookback", 100)
        .with_param("min_separation_atr", 1.5)
        .bind("atr14", "atr_14", "swing", "atr")
    .define("signal", "signal", "PullbackSignal")
        .with_param("min_strength", 0.5)
        .bind("swing", "four_swing_pullback", "signal", "pullback")
        .bind("ema20", "ema_20", "signal", "trend")
    .build()
)
```

## Related

- Backlog 036: AST model
- Backlog 038: Validation
