# 075: PortfolioBacktester core — merged calendar, shared tradebook

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** 074 (trade attribution)

## Description

New `PortfolioBacktester` (`backtesting/portfolio.py`). Runs a strategy across a
portfolio of instruments for the same period with **one shared tradebook**.

- Input: one `StrategyBundle`, `Sequence[tuple[Instrument, MarketStore]]`, shared `initial_balance`, `window_size`, `max_hold_days`.
- **Calendar merge**: primary-timeframe timestamps unioned across instruments, sorted ascending; `window_size` applies to the merged axis.
- **Per cursor**: each instrument aligns to its latest candle at or before the cursor timestamp (timestamp-based lookup, same as `MarketView.select`, 045). Per-instrument `MarketView` → graph run → signals; bundle `evaluate_all` per instrument; shared tradebook fill/resolve at the cursor candle of the **position's own instrument** (exit prices/stops never from another's).
- **Concurrency (explicit)**: one open trade at a time across the portfolio. First eligible signal in deterministic order (strategy priority, then instrument order) fills; others skipped while open. Concurrent positions are a non-goal.
- Risk engine sizing from the signal's own instrument facts/view. No-readahead: nothing after the cursor's aligned candle per instrument.
- Result: `PortfolioBacktestResult` — shared `tradebook`, per-instrument `FrameStore`s, per-instrument `Instrument` mapping (extend 063's `InstrumentBacktestResult`).
- `Backtester` (single-instrument) stays untouched.

## Acceptance Criteria

- [ ] Two instruments, same period, one shared tradebook: trades attributed to the correct canonical
- [ ] Calendar merge handles differing calendars (crypto + FX); each cursor aligns each instrument at latest candle ≤ cursor timestamp
- [ ] Open-trade resolution uses the position's own instrument candles (stop/target/max-hold/exit price)
- [ ] At most one open trade across the portfolio; deterministic fill order (strategy, then instrument)
- [ ] `TradeOutcome.instrument` populated on the portfolio path
- [ ] Shared balance compounds across instruments; `summary["by_instrument"]` correct
- [ ] No-readahead audit covers the portfolio path
- [ ] Tests: attribution, calendar alignment (offset calendars), single-open-trade constraint, shared balance compounding, deterministic ordering, portfolio result pickling

## Related

- Split from 070 (superseded); feeds 076 (CLI) and 077 (visualization)
- `src/marketatlas/backtesting/backtester.py` (reference only), `strategy/tradebook.py`, `analysis/ast/instrument.py`
