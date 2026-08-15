# 081: A/B comparison index — tables over the choice product

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** 079, 080

## Description

The "set of tables" option for portfolio A/B output: a static `ab.html` index
page that shows the existing portfolio info (summary bar + by-instrument +
by-strategy tables from `TradeBook.summary`, exactly as
`render_portfolio_index` does today) **across the product of all choice
combinations** — every variant side by side, no JS required.

Layout:

- A **summary grid**: one row per choice combination, columns = the choice
  values that identify it (from the 079/080 variant identity) + Trades, W-L,
  Win rate, P&L, Return, Max Drawdown, Profit factor, Expectancy.
- Per-combination **detail sections**: each variant gets the standard
  by-instrument and by-strategy tables, linked to its per-instrument charts in
  the 080 output tree.
- Reuse the existing index-page CSS/markup from `render_portfolio_index`
  (`portfolio.py`) — same `_sign_class`/`_fmt_*` helpers — so the A/B page
  looks like the existing portfolio page, not a new visual design.

Data comes only from each variant's `TradeBook.summary` — never recomputed.
The renderer accepts a `Sequence[(variant_identity, PortfolioBacktestResult)]`
so it is independent of where the variants came from (single-symbol A/B can
reuse the same grid with one-instrument detail).

This is the recommended v1: static, greppable, works from disk without a
server, and is the foundation for the interactive controls in 082.

## Acceptance Criteria

- [ ] `ab.html` renders a summary grid with one row per choice combination and
      the full summary metrics
- [ ] Per-combination by-instrument and by-strategy tables match
      `render_portfolio_index` output for the same variant's book
- [ ] Detail sections link to the per-variant charts from 080 via relative
      hrefs; the page opens from disk with no server
- [ ] Reuses `_sign_class`/`_fmt_*`/table styles from `portfolio.py` — no
      duplicated styling
- [ ] Single-symbol `--ab` reuses the same grid with one-instrument detail
- [ ] No JS on the page; `--no-js` is not a requirement, the page is plain HTML
- [ ] Tests: renderer unit test over a two-variant fixture asserting grid rows,
      detail tables, and hrefs; CLI test wiring `--ab` to the index
- [ ] `poetry run lint` green

## Related

- `src/marketatlas/visualization/portfolio.py` — `render_portfolio_index`,
  `_INDEX_TEMPLATE`, `_instrument_row`, `_strategy_rows_html`, `_fmt_*`
- `src/marketatlas/cli.py` — `_run_ab_test` (where the index is written)
- `src/marketatlas/backtesting/portfolio.py` — `PortfolioBacktestResult`
