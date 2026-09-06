# 104 — Boundary-candle max-hold cancel preempts stop/target

**Epic:** strategy

## Context

`TradeBook.resolve_at_cursor` (src/marketatlas/strategy/tradebook.py:243) decided
a trade's fate independently of its stop/target on the max-hold boundary candle.

Old order-of-checks:

```
days_held >= max_hold_days  →  _cancel_open(...)  →  return   # never checks stop/target
low <= stop / high >= target → close at stop/target            # unreachable on boundary
```

The `return` after the max-hold cancel meant a trade whose stop **or** target was
touched on the exact boundary candle was recorded as `cancelled` with `pnl=0`
instead of realizing the actual outcome.

Real impact observed in the 2026-01-29 30-instrument portfolio backtest:

- `AUDJPY` bullish, entry 108.046, target 110.474. Filled 2026-01-29. Candle
  2026-02-08 (= day 10, `max_hold_days=10`) traded high 110.79 ≥ 110.47 —
  intraday **target hit** — but the trade was recorded `cancelled`, pnl 0.
- `GBPAUD` bearish, identical signature: target 1.934 crossed 2026-02-08
  (high-touch) yet recorded `cancelled`.

Both were wins the span of one candle-touch. P&L understated by two winners.

This was surfaced by human notebook feedback (backlog 103): "the candle seems to
cross the target 3 days before 2026-02-10 — why is this marked as cancelled?"

## Scope

Evaluate stop/target on the boundary candle **before** falling through to the
max-hold cancellation. Stop-vs-target priority is unchanged (stop wins a same-day
double touch, matching pre-fix behavior). A boundary candle that touches neither
still cancels exactly as before.

## Requirements

- [x] Stop/target checks run before the `days_held >= max_hold_days` cancel, for
      both bullish and bearish.
- [x] A boundary candle touching the target closes as a `win`; touching the stop
      closes as a `loss`; touching neither cancels (`pnl=0`).
- [x] Stop-over-target same-day priority preserved (stop checked first).

## Testing

- [x] `tests/test_tradebook.py::test_boundary_candle_target_hit_closes_win_not_cancel`
- [x] `tests/test_tradebook.py::test_boundary_candle_stop_hit_closes_loss_not_cancel`
- [x] `tests/test_tradebook.py::test_bearish_boundary_candle_target_hit_closes_win`
- [x] `tests/test_tradebook.py::test_max_hold_cancels_not_breakeven` adjusted:
      boundary candle tightened to `h=104 lo=96` so it no longer touches target
      105 / stop 95 (the old defaults happened to touch stop, which is now a loss,
      not a cancel — the test's intent was "a held trade cancels, not breakeven").

Regression: `pytest -m "tier1 or tier2"` 817 passed.

Depends on: 096, 097 (feedback surfaced it), 103.