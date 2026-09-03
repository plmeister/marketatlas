# 098 — Performance data foundation: exit reason, MFE/MAE, realized R, equity curve

**Epic:** metrics
**Priority:** high

## Context

Goal is a strategy that doubles account value yearly, evaluated measurably. R
must become the canonical unit throughout the backtester (risk = 1% of equity,
so each trade's R = pnl / risk_at_that_trade). Before any advanced metric can
be computed, the backtester must *capture* data it currently throws away:

- **Exit reason** is lost: `resolve_at_cursor` in `strategy/tradebook.py`
  closes via stop or target but never records which; timeout collapses to
  `"cancelled"`. Signal-reversal exits don't exist yet.
- **MFE/MAE** are never tracked: the backtester only evaluates at stop/target
  close; intra-trade excursion is never observed, so "does the exit let winners
  run / stop too early" cannot be measured.
- **Realized R** not stored per trade (derivable as `pnl / candidate.risk_amount`
  but not serialized).
- **JSON trade payload** (`_trade_to_dict` in `frames/jsoncodec.py`) omits
  `exit_ts`, `size`, `risk_amount`, `R` — only in the richer HTML payload.
- **No equity curve**: `TradeLedger` keeps running balance + peak only, no
  time-indexed balance series, so CAGR/Sharpe/Sortino/drawdown-duration are
  impossible.

This backlog lays the data foundation every subsequent metric dashboard (099,
100, 101, 102) consumes. It changes capture + serialization, nothing downstream
yet (downstream metrics are subsequent backlogs).

## Requirements

### Exit reason
- [ ] Add a closed-exit-reason representation (enum or string constants):
      `stop`, `target`, `timeout`, `cancel` (never filled / broker), and later
      `reversal`. Document values.
- [ ] Record reason on `TradeOutcome` (new field, default None for back-compat).
- [ ] `resolve_at_cursor` passes through whether stop or target was hit.
- [ ] `_cancel_open` (timeout) records `timeout`; `_cancel_pending` records
      `cancel`; actual stop/target closes record their respective reason.
- [ ] `close_trade` / close paths accept and store the reason.
- [ ] Result mapping stays intact (win/loss/breakeven/cancelled derived from
      pnl + reason, not replaced by reason).

### MFE / MAE
- [ ] Add `mfe` / `mae` fields to `TradeOutcome` (in account currency).
- [ ] Backtester hook at each cursor while a trade is open: mark the open
      position's high/low against entry to track max favourable excursion and
      max adverse excursion. Intra-trade observation point must respect
      realistic fill (only evaluate on candle open/close the strategy sees —
      no lookahead; reuse existing candle-visibility discipline).
- [ ] MFE/MAE in **R units** too (mfe/risk_amount, mae/risk_amount) so exit
      quality is comparable across trades.
- [ ] Only update MFE/MAE while position is open during the loop; freeze at
      exit.

### Realized R + enriched payload
- [ ] Compute realized R per closed trade = `pnl / candidate.risk_amount`
      (guard risk_amount == 0 → None).
- [ ] Add to JSON `_trade_to_dict`: `exit_ts`, `size`, `risk_amount`, `r`,
      `mfe`, `mae`, `mfe_r`, `mae_r`, `exit_reason`.
- [ ] Keep `rr_ratio` (planned R:R) distinct from realized `r`.
- [ ] HTML trade payload (`interactive.py _extract_trades_json`) picks up same
      new fields for consistency (single source of truth = JSON codec).

### Equity curve
- [ ] `TradeLedger` records a time-indexed balance series (per closed-trade or
      per-candle, decide granularity; enough for annualization + drawdown).
- [ ] Expose the equity curve (timestamps + balance) through the JSON output so
      renderers/computations can consume it.
- [ ] Keep existing `balance`, `peak_balance`, `total_pnl`, `max_drawdown`
      behaviour unchanged (additive).

## Data flow change
```
TradeBook.resolve_at_cursor
   → record exit reason (stop/target/timeout)
   → update MFE/MAE each cursor
   → on close: compute realized R = pnl / risk_amount
TradeLedger → append (timestamp, balance) to equity curve
JSON codec → emit exit_ts, size, risk_amount, r, mfe, mae, mfe_r, mae_r,
             exit_reason + equity curve
```

## Testing
- [ ] `tests/test_tradebook.py`: stop vs target exits set distinct reasons;
      timeout → `timeout`; cancelled → `cancel`.
- [ ] MFE/MAE: fixture trade that dips then rallies — assert `mae` reflects the
      dip, `mfe` the rally, both frozen at exit; R-units correct.
- [ ] Realized R: positive/negative/breakeven pnl → correct R; zero-risk →
      None.
- [ ] JSON round-trip includes all new fields; no lookahead (excursion only
      from candle data the open position could have seen).
- [ ] Equity curve: series length matches closed trades, balance monotonic
      consistency with ledger final_balance.
- [ ] Existing tier1/tier2 snapshot/backtest tests stay green (fields additive).

Depends on: none (foundation).
Unblocks: 099, 100, 101, 102.
