# 102 — Backtest robustness + metrics report/CLI

**Epic:** metrics

## Context

Trades (099), portfolio (100), costs (101) give a point estimate of
performance. Point estimates fool people — a strategy that seems to double
yearly may be luck. This backlog adds the **robustness layer** (confidence
around the estimate) and a **single report command** that surfaces the whole
metrics dashboard (098-101) so the performance is judged on variance, not
just the headline number.

## A. Robustness (Monte Carlo + segmentation)

- [ ] Monte Carlo trade-order shuffling: resample the realized trade sequence
      (and/or equity-curve path) N times → distribution of CAGR, max drawdown,
      expectancy, probability of negative return over 1/3/5 years.
- [ ] Monte Carlo variation of individual trade outcomes (parametric resample
      of R distribution as alternative to pure shuffle).
- [ ] Confidence intervals around returns/expectancy (percentiles of MC dist).
- [ ] Worst-case plausible drawdown (e.g. P95/P99 of MC max drawdown).
- [ ] Probability of negative return over 1/3/5 years (compounded MC paths).
- [ ] Out-of-sample: train/test split + walk-forward evaluation flag on the
      result (in-sample vs out-of-sample metrics, gap reported).
- [ ] Performance across different periods (per-year) and across instruments —
      reuse existing by-instrument/by-strategy breakdown, surface variance.
- [ ] Parameter sensitivity stub: re-run with nudged params, report how CAGR/
      DD move (driveable later from strategy config).

## B. Report command

- [ ] `marketatlas metrics report` (or `marketatlas report`) CLI command that
      assembles 099+100+101(+102 robustness) into one output.
- [ ] Inputs: enriched JSON (098) + optional cost schedule (101) + optional
      robustness params (102).
- [ ] Outputs: `--format text` (CLI table) and `--format json` (full machine
      payload). Seed the HTML index/dashboard for visual use.
- [ ] Clear "does it double?" verdict line: CAGR vs 100%/yr target, with the
      MC confidence band (e.g. "CAGR 45% [P5-P95: 20-75%], not reliable").
- [ ] Report references the R-canonical framing throughout.

## Design

- [ ] `src/marketatlas/metrics/__init__.py` exports the dashboard entrypoint.
- [ ] `metrics/robustness.py` (Monte Carlo, CIs, walk-forward).
- [ ] `metrics/report.py` (assembles all layers, formats text/json).
- [ ] CLI wiring in `cli/commands.py` + subparser in `cli/__init__.py`.
- [ ] Deterministic RNG seed for reproducibility of MC runs.

## Testing

- [ ] MC shuffle: seeded run reproducible; P5/P95 sane on fixture.
- [ ] Walk-forward split correctness (no leakage).
- [ ] Report text/json: exact shape, empty-trades handled, no-provider not
      applicable (pure compute, no LLM).
- [ ] End-to-end: fixture JSON → report with all layers populated.

Depends on: 098 (data), 099, 100, 101.
