# 045: Multi-Resolution MarketView

**Status:** pending
**Epic:** core
**Priority:** medium

## Description

`MarketView` becomes the single multi-resolution data source for all analyzers. Data at each resolution is already in the store (fetched separately — see 046). MarketView provides the right resolution when an analyzer requests it, handles lookahead prevention consistently, and tags facts with their resolution for cross-timeframe routing.

## Acceptance Criteria

- [ ] `MarketView` accepts/contains data at multiple resolutions (daily, weekly, etc.) from `MarketStore`
- [ ] Analyzer declares target timeframe (default: strategy base timeframe)
- [ ] `MarketView.select(timeframe)` returns a view at that resolution with correct cursor alignment for lookahead prevention
- [ ] Lookahead prevention works across resolutions: weekly view at week N covers only data through that week's end, not future weeks
- [ ] Facts tagged with source timeframe (e.g. `FactKey("swing", timeframe="1w")`)
- [ ] Analyzer `requires()` references include timeframe so dependency resolution works cross-resolution
- [ ] `SupportResistanceAnalyzer` on weekly data produces stable SR levels immune to daily candle additions
- [ ] At least one end-to-end test: weekly swing + daily pullback with correct fact propagation

## Technical Notes

- MarketView stores references to multiple `Candle` series (pre-fetched), indexed by `Timeframe`
- Cursor alignment: given daily cursor at day D, weekly cursor is the last completed week ≤ D
- `FactKey` gains optional `timeframe` field; `FactKey("swing", timeframe="1w")` is distinct from `FactKey("swing", timeframe="1d")`
- Execution order: higher-res (lower TF number) runs first since it covers less data per tick; lower-res (higher TF) sees the full picture
- Missing data for requested TF is valid: analyzer returns empty result or error evidence

## Related

- `src/marketatlas/data/view.py` — `MarketView` (primary target)
- `src/marketatlas/data/store.py` — `MarketStore` (holds multi-res data)
- `src/marketatlas/analysis/base.py` — `Analyzer` base (timeframe param, FactKey update)
- `src/marketatlas/analysis/factkey.py` — `FactKey` (add timeframe)
- Backlog 046: Multi-timeframe data fetching
