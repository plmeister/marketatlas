# 093: Cache MarketView computed properties

**Status:** pending
**Epic:** performance
**Priority:** high

## Description

`MarketView` computes `prices`, `highs`, `lows`, `volumes`, and `timestamps` by building new tuples on every property access (`view.py:48-65`). Each analyzer calls these multiple times per frame. With 9554 frames × 9 analyzers, this creates thousands of throwaway tuples.

`history` is already sliced once per access but the derived properties rebuild from it independently.

## Design

1. Cache the underlying `history` tuple on first access (it's the bottleneck for all derived properties)
2. Derived properties (`prices`, `highs`, etc.) iterate over the cached history + current once and cache the result
3. Since `MarketView` is a frozen dataclass, use a private `_history_cache: tuple[Candle, ...] | None = None` slot + manual invalidation isn't needed (cursor is immutable)
4. Alternative: replace `@dataclass(frozen=True)` with a `__slots__` class that lazily caches, or just use `functools.lru_cache` on the property (works if we add `__hash__`)

Simplest approach: since `cursor`, `window_size`, `store`, and `view_timeframe` are all immutable after construction, add a `_history` lazy slot and cache `prices`/`highs`/`lows`/`volumes`/`timestamps` the first time they're accessed.

## Files

- `data/view.py` — add `_history` cache slot, modify `history`, `prices`, `highs`, `lows`, `volumes`, `timestamps`

## Testing

**IMPORTANT:** Run `poetry run pytest` (full suite, NO `-x`). Collect ALL failures
in one pass, fix them all, then run again to verify. Do NOT use `pytest -x` —
it wastes time fixing one failure at a time and risks timeout.

## Acceptance Criteria

- [ ] `MarketView` caches `history` tuple (only slices store once per cursor position)
- [ ] `prices`, `highs`, `lows`, `volumes`, `timestamps` are computed from cached history
- [ ] All existing tests pass — output must be identical (same tuples, same values)
- [ ] `poetry run pytest` — full suite green

## Related

- `data/view.py:34-40` — `history` property (slices every call)
- `data/view.py:48-65` — `prices`/`highs`/`lows`/`volumes`/`timestamps` (rebuild tuples every call)
- `analysis/analyzers/ema.py:29` — `view.prices` called per analyze()
