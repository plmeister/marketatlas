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

- [x] Monte Carlo trade-order shuffling: resample the realized trade sequence
      (and/or equity-curve path) N times → distribution of CAGR, max drawdown,
      expectancy, probability of negative return over 1/3/5 years.
- [x] Monte Carlo variation of individual trade outcomes (parametric resample
      of R distribution as alternative to pure shuffle).
- [x] Confidence intervals around returns/expectancy (percentiles of MC dist).
- [x] Worst-case plausible drawdown (e.g. P95/P99 of MC max drawdown).
- [x] Probability of negative return over 1/3/5 years (compounded MC paths).
- [x] Out-of-sample: train/test split + walk-forward evaluation flag on the
      result (in-sample vs out-of-sample metrics, gap reported).
- [x] Performance across different periods (per-year) and across instruments —
      reuse existing by-instrument/by-strategy breakdown, surface variance.
- [x] Parameter sensitivity stub: re-run with nudged params, report how CAGR/
      DD move (driveable later from strategy config).

## B. Report command

- [x] `marketatlas metrics report` (or `marketatlas report`) CLI command that
      assembles 099+100+101(+102 robustness) into one output.
- [x] Inputs: enriched JSON (098) + optional cost schedule (101) + optional
      robustness params (102).
- [x] Outputs: `--format text` (CLI table) and `--format json` (full machine
      payload). Seed the HTML index/dashboard for visual use.
- [x] Clear "does it double?" verdict line: CAGR vs 100%/yr target, with the
      MC confidence band (e.g. "CAGR 45% [P5-P95: 20-75%], not reliable").
- [x] Report references the R-canonical framing throughout.

## Design

- [x] `src/marketatlas/metrics/__init__.py` exports the dashboard entrypoint.
- [x] `metrics/robustness.py` (Monte Carlo, CIs, walk-forward).
- [x] `metrics/report.py` (assembles all layers, formats text/json).
- [x] CLI wiring in `cli/commands.py` + subparser in `cli/__init__.py`.
- [x] Deterministic RNG seed for reproducibility of MC runs.

## Testing

- [x] MC shuffle: seeded run reproducible; P5/P95 sane on fixture.
- [x] Walk-forward split correctness (no leakage).
- [x] Report text/json: exact shape, empty-trades handled, no-provider not
      applicable (pure compute, no LLM).
- [x] End-to-end: fixture JSON → report with all layers populated.

Depends on: 098 (data), 099, 100, 101.
