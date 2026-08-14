# 077: Portfolio visualization — index page + per-instrument charts

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** 074 (attribution), 075 (PortfolioBacktester)

## Description

Visual output for portfolio runs.

- **Per-instrument chart**: reuse `InteractiveRenderer` as-is; `TRADES` filtered to that instrument's trades from the shared tradebook (074 gives the filter key). Chart title carries the canonical name.
- **Index page** (`visualization/portfolio.py`, e.g. `render_portfolio_index`): lightweight self-contained static HTML, no charting lib — portfolio summary bar (shared balance, total P&L, return, drawdown, trade counts) + table of instruments: canonical name, per-instrument P&L / trades / W-L / win rate / profit factor, one row each, each name links to its per-instrument HTML chart. Optional summary table by strategy.
- **Naming**: instrument charts `{stem}.{canonical}.html`, index `{stem}.html` written alongside in the output directory.

## Acceptance Criteria

- [ ] Per-instrument chart trade markers reflect only that instrument's trades
- [ ] Index page renders: one row per instrument (P&L/trades/W-L/win rate/PF), links to per-instrument charts, portfolio summary from the shared book
- [ ] Index + per-instrument chart files named/placed per the naming rule; index works from disk (relative links, no server)
- [ ] `by_instrument` stats come from `TradeBook.summary` — no recompute
- [ ] `test_html_output_validation`/`test_interactive_renderer` extend: one family asserts per-instrument charts' `TRADES` arrays contain only matching instruments; another asserts index rows + hrefs

## Related

- Split from 070 (superseded); consumes 074 + 075
- `src/marketatlas/visualization/interactive.py`, `visualization/portfolio.py` (new)
