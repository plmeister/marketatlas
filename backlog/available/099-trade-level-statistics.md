# 099 — Trade-level statistics (R-distribution engine)

**Epic:** metrics

## Context

Data foundation (098) now captures per-trade exit reason, MFE/MAE, and realized
R. This backlog turns that into the trade-level metrics dashboard: everything
measured per trade, in **R units** (R canonical — no currency tangle).

Computation lives in a dedicated metrics module that consumes the enriched JSON
(098) or the live `TradeBook` — single derived layer, not scatter across the
backtester.

## Metrics to produce (all in R unless noted)

- [ ] Trade count (total, and by outcome: wins/losses/breakevens).
- [ ] Win rate (% of R>0 trades; flag how breakevens/cancels are counted).
- [ ] Average win (R), average loss (R) — mean and median.
- [ ] Expectancy per trade (R) = mean of realized R over all closed trades
      (define whether cancels with R=0 count).
- [ ] Profit factor = gross profit (R) / gross loss (R).
- [ ] R distribution: histogram buckets, min/max, quartiles/percentiles
      (P1/P5/P25/P50/P75/P95/P99), skew/kurtosis.
- [ ] Max win (R), max loss (R).
- [ ] Average trade duration (time in market), by outcome.
- [ ] Realized R vs MFE (R) — the "exits too early?" signal:
      % of winners that exceeded 1R/2R/3R/4R in MFE but exited at less;
      how far below MFE the average exit sits.
- [ ] MAE distribution / median MAE (R) — stop-distance sanity.
- [ ] Exit-reason breakdown: shares of stop/target/timeout/cancel/reversal,
      and win rate / avg R per exit reason.
- [ ] Trade frequency: trades per day/week/month (timeframe-aware).
- [ ] % of trades reaching 1R/2R/3R/4R (by realized R AND by MFE), separately
      for long/short.

## Design

- [ ] New module `src/marketatlas/metrics/trades.py`.
- [ ] Pure functions: `trade_metrics(trades: list[dict]) -> dict` operating on
      the enriched trade dicts (098) → JSON-serializable, unit-testable, no I/O.
- [ ] Reusable histogram/percentile helpers in `metrics/stats.py`.
- [ ] Output schema documented; renderers (100) and report (102) consume it.

## Testing

- [ ] Fixture trade set with known wins/losses/R → exact expected metrics.
- [ ] Edge cases: empty trade list, zero gross loss (→ pf infinity/None),
      all-breakeven, single trade, zero risk (R=None skipped).
- [ ] Percentile/median correctness vs numpy reference on a random dataset.
- [ ] MFE-vs-realized checks: hand-build a trade that MFE'd 3R then closed at
      1R → flagged as left-on-the-table.

Depends on: 098.
Unblocks: 100, 102.
