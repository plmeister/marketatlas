# 076: CLI portfolio run path

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** 075 (PortfolioBacktester)

## Description

Wire `run --instruments <file>` to execute the portfolio path end-to-end. Today
the CLI stops after `PORTFOLIO DATA` — the backtest never runs.

- `run --instruments` loads the portfolio (069), runs `PortfolioBacktester` (075), prints portfolio summary + `by_instrument` + `by_strategy`
- `--output` names the result output (index); per-instrument artifacts derived from its stem
- Single-`--symbol` run unchanged

## Acceptance Criteria

- [ ] `run --instruments` completes: data load → portfolio backtest → summary output
- [ ] Summary prints shared balance, total P&L, return, drawdown, trade counts + `by_instrument` + `by_strategy`
- [ ] Single-`--symbol` run unchanged (existing CLI tests pass)
- [ ] Exit code reflects success/failure; data-load failures per instrument are reported, not fatal to the run

## Related

- Split from 070 (superseded); consumes 075
- `src/marketatlas/cli.py`, `data/portfolio.py`
