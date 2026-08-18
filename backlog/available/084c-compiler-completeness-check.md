# 084c: Compiler enforces input completeness

**Status:** pending
**Epic:** ast
**Priority:** high
**Depends on:** 084b

## Description

After 084b, every provider has a contract declaring its required inputs. But the compiler never checks that a definition supplies all contract-declared inputs. You can write `trend { ema_20: ema20, ema_50: ema50 }` (omitting `atr_14`) and it compiles — the analyzer picks up whatever `atr_14` fact exists at runtime.

**Goal:** Missing required inputs → compile error naming the definition and the missing fact.

## Design

1. Add a new compiler pass `CompletenessPass` (or add to `RegistryResolutionPass`) that runs after registry resolution
2. For each definition, look up its provider's contract inputs
3. Check that every contract input has a corresponding `ReferenceExpression` parameter in the definition
4. Missing → `CompilationError(f"definition '{name}' is missing required input '{missing_fact}'")`
5. Run this pass in stage 1 (after registry resolution, before expansion)

## Files

- `analysis/ast/pipeline.py` — add `CompletenessPass` or extend `RegistryResolutionPass`
- `analysis/ast/pipeline.py` — register the pass in the pipeline

## Acceptance Criteria

- [ ] `trend { ema_20: ema20, ema_50: ema50 }` (omitting `atr_14`) fails to compile with error naming `atr_14`
- [ ] `trend { ema_20: ema20, ema_50: ema50, atr_14: atr14 }` compiles successfully
- [ ] `generate_signal { pullback_pattern: pp, trend: t, atr_14: a }` compiles
- [ ] `generate_signal { pullback_pattern: pp, trend: t }` (omitting `atr_14`) fails
- [ ] Error message includes definition name and missing fact name
- [ ] Existing tests pass (all current DSL configs are complete)
- [ ] `poetry run pytest -m tier1` green

## Related

- `analysis/ast/lowering.py:244-276` — parameter resolution loop
- `analysis/ast/registry.py:29-30` — `ProviderContract.inputs`
- `analysis/ast/pipeline.py:135` — `RegistryResolutionPass`
