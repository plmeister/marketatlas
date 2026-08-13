# 074: Trade attribution — instrument field on TradeOutcome

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** none (foundation for 075/076/077)

## Description

`TradeOutcome` has `source_strategy` but no instrument — portfolio trades cannot
be attributed to their canonical instrument. Add `instrument: str` (canonical)
to `TradeOutcome` and thread it through `submit_order`/`fill_order`/`close_trade`
via a new `instrument` param. `TradeBook.summary` gains a `by_instrument`
breakdown (mirroring `by_strategy`). Single-instrument `Backtester` passes its
store's canonical symbol — existing tests keep passing, trades now attributed.

## Scope

- `strategy/trade.py`: `TradeOutcome.instrument` field
- `strategy/tradebook.py`: `instrument` param through order lifecycle; `summary["by_instrument"]`
- `backtesting/backtester.py`: pass canonical store symbol
- CLI trade log gains an instrument column

## Acceptance Criteria

- [ ] `TradeOutcome.instrument` populated for single-instrument runs (canonical symbol)
- [ ] `summary["by_instrument"]` correct; matches `by_strategy` structure
- [ ] CLI trade log shows instrument column
- [ ] All existing tests pass unchanged in behavior (attribution additive)

## Related

- Split from 070 (superseded); prerequisite for 075/076/077
- `src/marketatlas/strategy/tradebook.py`, `strategy/trade.py`, `backtesting/backtester.py`
