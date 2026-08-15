# 079: Portfolio A/B test runner

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** 048, 050, 051, 063, 075, 076

## Description

`marketatlas run --ab` currently handles only the single-symbol path
(`run_command`); the `--instruments` portfolio path (`run_portfolio_command`)
ignores `--ab` and compiles a single `StrategyConfig` via `load_strategy`.
Choice templates (`<a | b | c>`) are therefore not A/B testable across a
portfolio.

Add portfolio A/B: when `--ab` and `--instruments` are both set, expand the
choice template with `ASTCompiler.compile_templates`, run
`PortfolioBacktester` once per concrete variant with a **fresh
`StrategyBundle` per variant** (isolated analyzers + tradebook, matching the
single-instrument `--ab`), and print a text comparison.

Variant identity must be deterministic and human-readable. Generalize the
current `_variant_label` (reads only signal rules) to diff a variant against
its neighbours across **all** definitions — analyzer params, signal rules, and
risk params — so a choice on any node (e.g. `max_stop_atr: <3 | 5>`) is
labeled. Ordering follows `compile_templates` expansion order (already
deterministic, column-major cartesian). Choice-free DSLs yield exactly one
variant, so `--ab` stays backward compatible with ordinary strategy files.

## Acceptance Criteria

- [ ] `run --ab --instruments <portfolio.yaml> --strategy <s.dsl>` runs one
      portfolio backtest per concrete variant and prints a comparison (trades,
      W/L, P&L, return, drawdown, PF, expectancy) with choice-value labels
- [ ] Variant label names the chosen values on any node type (analyzer, signal,
      risk), not just `generate_signal` rules
- [ ] Each variant runs on its own `StrategyBundle`/`TradeBook` — no
      cross-variant state contamination (assert distinct tradebook objects)
- [ ] Choice-free `.dsl` under `--ab` produces exactly 1 variant and runs
      normally
- [ ] `--ab` with a `.yaml` strategy file errors cleanly (`.dsl` required)
- [ ] Shared fetch/store setup extracted into one helper used by both the
      single-symbol and portfolio `--ab` paths (no duplicated fetch logic)
- [ ] New tests: mocked CLI tests for flag wiring + a real two-instrument /
      two-value-choice fixture asserting result counts and labels
- [ ] `poetry run lint` green

## Related

- `src/marketatlas/cli.py` — `run_command`/`run_portfolio_command`, current
  single-symbol `--ab` (`_run_ab_test`, `_variant_label`)
- `src/marketatlas/backtesting/portfolio.py` — `PortfolioBacktester`
- `src/marketatlas/analysis/ast/compiler.py` — `compile_templates`
- `src/marketatlas/strategy/bundle.py` — `StrategyBundle`
