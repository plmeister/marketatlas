# 100 — Portfolio / equity performance metrics

**Epic:** metrics

## Context

Trade stats (099) answer "are individual trades good?". This backlog answers
"does the portfolio compound and survive?" — equity/portfolio-level metrics
from the equity curve and trade history (098).

## Metrics to produce

Return & compounding:
- [ ] Total return (%), final/initial balance.
- [ ] CAGR / annualised geometric return (from equity curve, see design).
- [ ] Monthly and annual (compounded) returns.
- [ ] Compounded vs simple return signal.

Risk & drawdown:
- [ ] Maximum drawdown (%) from the equity curve (peak-to-trough), and its
      peak/trough dates + duration (bars).
- [ ] Average drawdown, average drawdown duration, longest time to recover.
- [ ] Volatility of period returns (annualised std of log returns).
- [ ] Sharpe ratio (period returns vs risk-free, annualised).
- [ ] Sortino ratio (downside deviation).
- [ ] Calmar ratio = CAGR / max drawdown.
- [ ] Risk of ruin / probability of substantial loss (see robustness notes in
      102 for Monte Carlo; here heuristic from drawdown distribution).

Equity behavior:
- [ ] Max consecutive losses, max consecutive wins.
- [ ] Largest peak-to-trough loss.
- [ ] Simulated equity curve series (from 098) exposed for rendering.

Exposure / risk:
- [ ] Risk per trade (%, current 1%), max simultaneous exposure (overlapping
      open trades), average exposure.
- [ ] Exposure by instrument/market, correlation of simultaneous positions.

## Design

- [ ] New module `src/marketatlas/metrics/portfolio.py`.
- [ ] Pure functions on (equity curve, trades) → dict; JSON-serializable.
- [ ] Period-returns helper in `metrics/stats.py` (log returns, vol, sharpe,
      sortino) reused across 100/102.
- [ ] Drawdown engine in `metrics/drawdown.py`: operating on balance series,
      returns duration + recovery, not just max (extends TradeLedger's
      realized-pnl-only version to the time series).
- [ ] Decide & document risk-free-rate and annualisation basis (bars per year
      from timeframe; default risk-free 0 for backtest comparison).

## Testing

- [ ] Hand-built equity curve → exact CAGR, max DD + dates, duration, Sharpe,
      Sortino, Calmar (verify against independent numpy computation).
- [ ] Zero-downside series → Sortino defined handling.
- [ ] Drawdown duration/recovery correctness on a sequence with one deep DD.
- [ ] Consecutive win/loss streaks from a known trade sequence.
- [ ] Exposure: overlapping trades fixture → max simultaneous correct.

Depends on: 098.
Unblocks: 101 (costs), 102 (robustness + report).
