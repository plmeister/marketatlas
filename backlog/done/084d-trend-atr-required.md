# 084d: Make TrendAnalyzer require atr_14

**Status:** done
**Epic:** ast
**Priority:** high
**Depends on:** 084c

## Description

`TrendAnalyzer` uses ATR for strength calculation but treats it as optional (`facts.get` with fallback to price-based strength at `trend.py:55`). The DSL doesn't need to declare `atr_14` for trend — it picks up whatever `atr_14` fact exists.

After 084c, the compiler validates completeness. `TrendAnalyzer.requires()` must include `atr_14` so its contract lists it, and `strategy/swing.dsl` must declare it.

## Design

1. `TrendAnalyzer.requires()` adds `FactKey("atr_14")`
2. Remove the `facts.get(atr_key)` fallback — hard error if ATR is missing (the compiler prevents this now)
3. Update `strategy/swing.dsl` trend node: add `atr_14: atr_14`
4. Update any test DSL strings that define trend without `atr_14`

## Files

- `analysis/analyzers/trend.py` — `requires()`: add atr_14
- `strategy/swing.dsl` — trend node: add `atr_14: atr_14`
- `tests/test_dsl_integration.py` — update DSL strings if needed

## Testing

**IMPORTANT:** Run `poetry run pytest` (full suite, NO `-x`). Collect ALL failures
in one pass, fix them all, then run again to verify. Do NOT use `pytest -x` —
it wastes time fixing one failure at a time and risks timeout.

## Acceptance Criteria

- [x] `TrendAnalyzer.requires()` includes `FactKey("atr_14")`
- [x] `strategy/swing.dsl` trend node has `atr_14: atr_14`
- [x] Trend analysis without ATR raises (no silent fallback)
- [x] All tests pass
- [x] `poetry run pytest` — full suite green (1316+ tests)

## Related

- `analysis/analyzers/trend.py:16-18` — current requires()
- `analysis/analyzers/trend.py:55` — ATR fallback
- `strategy/swing.dsl` — trend node definition
