# 084e: PullbackSignal consumes DSL-injected keys

**Status:** pending
**Epic:** ast
**Priority:** high
**Depends on:** 084c

## Description

`PullbackSignal` uses constructor key defaults (`pullback_key="pullback_pattern"`, etc.) and `resolve_fact_key` to find facts by name. When compiled from DSL, the compiler injects explicit keys into `SignalConfig.rules` — but `PullbackSignal` ignores them and falls back to its own defaults.

**Goal:** When compiled from DSL, `PullbackSignal` uses the injected keys from `SignalConfig.rules` instead of constructor defaults.

## Design

1. `PullbackSignal` constructor gains optional `bindings: dict[str, str] | None = None` param (matching `RiskEngine` pattern)
2. When `bindings` is provided, use `bindings["pullback_pattern"]` etc. instead of `self._pullback_key`
3. The compiler already injects `bindings` into `SignalConfig.rules` for reference expressions (lowering.py:261-262) — verify this flows through
4. Constructor defaults remain for programmatic construction

## Files

- `analysis/signals/pullback_signal.py` — constructor + `evaluate()` key resolution
- `tests/test_signal_system.py` — add test for injected keys path

## Testing

**IMPORTANT:** Run `poetry run pytest` (full suite, NO `-x`). Collect ALL failures
in one pass, fix them all, then run again to verify. Do NOT use `pytest -x` —
it wastes time fixing one failure at a time and risks timeout.

## Acceptance Criteria

- [ ] DSL-compiled `PullbackSignal` uses injected keys from `SignalConfig.rules["bindings"]`
- [ ] Programmatic construction still works with defaults
- [ ] `strategy/swing.dsl` compiles and the signal uses the correct fact keys
- [ ] All tests pass
- [ ] `poetry run pytest` — full suite green (1316+ tests)

## Related

- `analysis/signals/pullback_signal.py:28-44` — current constructor + evaluate
- `analysis/ast/lowering.py:261-262` — bindings injection
- `strategy/risk.py:34` — `RiskEngine` bindings pattern to follow
