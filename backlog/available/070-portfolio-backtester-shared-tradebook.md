# 070: Portfolio Backtester — Shared TradeBook with Instrument Attribution

**Status:** in-progress  
**Epic:** portfolio  
**Priority:** high

## Description

Run a strategy across a portfolio of instruments for the same period, keep a **single shared tradebook**, and record which instrument each trade belongs to. Today:

- `backtest_template` (063) runs per-instrument backtests with **separate** tradebooks — no capital is shared, no portfolio-level book exists.
- `TradeOutcome` has `source_strategy` but no instrument field — trades cannot be attributed.
- The single-instrument `Backtester` walks one primary-timeframe candle series; a portfolio needs time-aligned iteration across instruments with different calendars (crypto trades weekends, FX does not; differing holidays).

## Goal

- A `PortfolioBacktester` that advances all instruments in lockstep over a **merged calendar** (union of per-instrument primary-timeframe timestamps), evaluates the strategy bundle across instruments at each cursor, and routes fills/exits through **one shared `TradeBook`**.
- Every `TradeOutcome` carries the canonical instrument name.
- `TradeBook.summary` gains a `by_instrument` breakdown (mirroring `by_strategy`).
- Single-instrument runs keep working, now with the instrument attributed.

## Concurrency decision (explicit)

`TradeBook` today holds at most one open trade. V1 therefore trades **one position at a time across the whole portfolio** (single open trade, shared capital). At each cursor, the first eligible signal in deterministic order (strategy priority order, then instrument order) fills; others are skipped while a position is open. Concurrent per-instrument positions are an explicit non-goal — the shared-book design deliberately leaves the door open (per-instrument `_open_trade` slots) but v1 stays sequential.

## Scope

- **Attribution**:
  - Add `instrument: str` (canonical) to `TradeOutcome`; thread through `submit_order`/`fill_order`/`close_trade` (a new `instrument` param).
  - Single-instrument `Backtester` passes its store's canonical symbol — existing tests keep passing, trades now attributed.
  - `by_instrument` breakdown in `TradeBook.summary`; CLI trade log gains an instrument column.
- **`PortfolioBacktester`** (new, `backtesting/portfolio.py`):
  - Input: one `StrategyBundle`, `Sequence[tuple[Instrument, MarketStore]]`, shared `initial_balance`, `window_size`, `max_hold_days`.
  - **Calendar merge**: primary-timeframe timestamps unioned across instruments, sorted ascending; `window_size` applies to the merged axis. Each instrument aligns to its latest candle at or before the cursor timestamp (per-instrument index lookup — same timestamp-based alignment `MarketView.select` uses, 045).
  - **Per cursor**: per-instrument `MarketView` → graph run → signals; bundle `evaluate_all` per instrument; shared tradebook fill/resolve at the cursor candle of the **position's own instrument** (exit prices/stops must come from that instrument's candles, never another's).
  - Risk engine sizing uses the signal's own instrument facts/view.
  - No-readahead: nothing after the cursor's aligned candle per instrument.
  - Result: `PortfolioBacktestResult` — shared `tradebook`, per-instrument `FrameStore`s, per-instrument `Instrument` mapping (extend/reuse 063's `InstrumentBacktestResult`, adding the shared book at portfolio level).
- **Visualization**: per-instrument interactive HTML (one per instrument) + a **portfolio index page**:
  - Per-instrument chart: reuse `InteractiveRenderer` as-is; `TRADES` filtered to that instrument's trades from the shared tradebook (070 attribution gives the filter key). Chart title carries the canonical name.
  - Index page (`visualization/portfolio.py`, e.g. `render_portfolio_index`): lightweight self-contained static HTML, no charting lib — portfolio summary bar (shared balance, total P&L, return, drawdown, trade counts) + table of instruments: canonical name, per-instrument P&L / trades / W-L / win rate / profit factor, one row each, each instrument name links to its per-instrument HTML chart. Optional summary table by strategy.
  - File naming: instrument charts `{stem}.{canonical}.html`, index `{stem}.html` written alongside in the output directory.
- **CLI**: `run --instruments file` executes the portfolio path; prints portfolio summary + `by_instrument` + `by_strategy`; writes index page + per-instrument charts; `--output` names the index (per-instrument files derived from its stem).

## Non-Goals

- Concurrent / multiple simultaneous positions (see concurrency decision).
- Portfolio-level risk (position-size by total portfolio, correlation, per-instrument sub-accounts).
- Cross-instrument nodes in the portfolio run (064 groups are a separate path).

## Acceptance Criteria

- [ ] Two instruments, same period, one shared tradebook: trades attributed to the correct canonical
- [ ] Calendar merge handles differing calendars (crypto + FX); each cursor aligns each instrument at latest candle ≤ cursor timestamp
- [ ] Open-trade resolution uses the position's own instrument candles (stop/target/max-hold/exit price)
- [ ] At most one open trade across the portfolio; deterministic fill order (strategy, then instrument)
- [ ] `TradeOutcome.instrument` populated for both portfolio and single-instrument paths
- [ ] `summary["by_instrument"]` correct; CLI trade log shows instrument column
- [ ] Portfolio index page renders: one row per instrument (P&L/trades/W-L/win rate/PF), links to per-instrument charts, portfolio summary from the shared book
- [ ] Per-instrument chart trade markers reflect only that instrument's trades
- [ ] Index + per-instrument chart files named/placed per the naming rule; index works from disk (relative links, no server)
- [ ] Single-`--symbol` run unchanged (existing tests pass)
- [ ] No-readahead audit covers the portfolio path
- [ ] Tests: attribution, calendar alignment (offset calendars), single-open-trade constraint, shared balance compounding across instruments, deterministic ordering, portfolio result pickling

## Technical Notes

- `MarketStore` timestamps are per-symbol; the merged calendar is built from `store.timestamps` union. Per-instrument alignment = binary search on that instrument's timestamp array for the cursor timestamp.
- `TradeBook` is already shared-capital by construction (`_balance`); the portfolio path reuses it verbatim plus the new `instrument` param.
- Keep `Backtester` untouched for the single-instrument path; `PortfolioBacktester` mirrors its loop with the calendar + per-instrument views.
- Per-instrument frames stay isolated (`FrameStore` per instrument) so 024/027 visualization tests keep working.
- Index page stays dependency-free static HTML (same self-contained ethos as 015/024, minus the charting library). `by_instrument` stats come straight from `TradeBook.summary` — no recompute.
- Existing `test_html_output_validation`/`test_interactive_renderer` extend naturally: one test family asserts the per-instrument charts' `TRADES` arrays contain only matching instruments; another asserts the index rows + hrefs.

## Related

- Backlog 069 (portfolio file + data loading), 063 (per-instrument result shape), 045 (timeframe-aligned views), 022 (strategy-aware backtester), 067 (entry-gated signals feed this)
- `src/marketatlas/backtesting/backtester.py`, `src/marketatlas/strategy/tradebook.py`, `src/marketatlas/strategy/trade.py`, `src/marketatlas/analysis/ast/instrument.py`
- `src/marketatlas/visualization/interactive.py`, `src/marketatlas/visualization/portfolio.py` (new)
