# 084a: Add requires() to Signal and RiskEngine

**Status:** pending
**Epic:** ast
**Priority:** high
**Depends on:** 087

## Description

`Analyzer` subclasses declare their fact inputs via `requires()`/`produces()` (`analysis/base.py:50-53`). `Signal` and `RiskEngine` don't — they use constructor key defaults (`pullback_key="pullback_pattern"`, `atr_key="atr_14"`, etc.) that silently auto-locate facts by name.

This means the DSL can omit required inputs and the node picks up whatever fact matches the default name. No compile-time error.

**Goal:** Give `Signal` and `RiskEngine` a `requires()` method so the registry can derive contracts for them (084b).

## Design

1. **Signal base class** gets abstract `requires() -> tuple[FactKey, ...]` and `produces() -> tuple[FactKey, ...]` (default empty tuple for produces)
2. **PullbackSignal** implements `requires()` returning the three fact keys it consumes: `pullback_pattern`, `trend`, `atr_14`
3. **RiskEngine** gets `requires()` returning `atr_14`, `sr`, `swing` (its three fact inputs)
4. Existing constructor key defaults remain for programmatic/YAML construction paths
5. `_derive_contract` in `registry.py:161` already reads `requires()`/`produces()` — no changes needed there

## Files

- `strategy/signals.py` — `Signal` ABC: add `requires()`, `produces()`
- `analysis/signals/pullback_signal.py` — implement `requires()`
- `strategy/risk.py` — `RiskEngine`: implement `requires()`

## Acceptance Criteria

- [ ] `Signal.requires()` returns fact key names the signal consumes
- [ ] `PullbackSignal.requires()` returns `("pullback_pattern", "trend", "atr_14")`
- [ ] `RiskEngine.requires()` returns `("atr_14", "sr", "swing")`
- [ ] Existing tests pass (signals still work with default keys)
- [ ] `poetry run pytest -m tier1` green

## Related

- `analysis/base.py:50-53` — `Analyzer.requires()`/`produces()` pattern
- `analysis/ast/registry.py:161` — `_derive_contract` reads these methods
- `analysis/signals/pullback_signal.py:32-34` — current key defaults
- `strategy/risk.py:29-31` — current key defaults
