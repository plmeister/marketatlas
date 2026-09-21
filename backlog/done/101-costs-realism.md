# 101 — Costs & realism (net performance)

**Epic:** metrics

## Context

Metrics so far (098-100) are gross — they ignore the frictions a live account
pays. A strategy can look like it doubles yearly gross yet lose net. This
backlog layers realistic costs on the backtest and reports **net** performance
(and the gap, which is the real "edge survives?" question).

## Cost model

- Reify an explicit cost schedule (single point of truth), configurable per
  run rather than hard-coded:
  - [ ] Commission/fee: per-trade (flat and/or per-unit — contract/lot sizing).
  - [ ] Spread: entry and exit slippage pct (current `candidate.slippage_pct`
        exists — formalise and extend to exits).
  - [ ] Stop-loss slippage: adverse fill when stop is hit (gap-through).
  - [ ] Position-size rounding: effect of rounding lot/contract size on actual
        exposure and realised R.
  - [ ] Delayed execution / missed trades: what if fills slip a bar (see
        Monte Carlo in 102 for the probabilistic version; here deterministic
        offset toggle).

## Net metrics

- [ ] Gross vs net for: total return, CAGR, expectancy (R), profit factor,
      win rate.
- [ ] Net expectancy (R) per trade after costs.
- [ ] Return drag: net CAGR − gross CAGR, net PF − gross PF.
- [ ] Sign flip warning: metrics that change sign/worse-than-1 after costs.
- [ ] Break-even win rate at current costs (what win rate covers frictions).

## Design

- [ ] New module `src/marketatlas/metrics/costs.py`: applies a cost schedule
      to a trade list → net-adjusted R/pnl per trade.
- [ ] Cost schedule model (`dataclass`/config) in `strategy/` or `metrics/`,
      defaulted to zero so existing gross behaviour unchanged unless enabled.
- [ ] `--costs` CLI flag (path/JSON or inline) to enable; else gross.
- [ ] Keep gross metrics intact; net is additive/reported alongside.

## Testing

- [ ] Known cost schedule on fixture trades → exact net R/pnl.
- [ ] Slip-through-stop fixture → adverse fill beyond stop.
- [ ] Zero-cost schedule → net == gross (back-compat guard).
- [ ] Rounding of size → exposure + R deltas correct.
- [ ] CLI: gross default unchanged; `--costs` turns net on.

Depends on: 100 (reuses net return/CAGR), 098 (R + equity).
Unblocks: 102 (report includes net).
