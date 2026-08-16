# 091: Split views.js into single-responsibility chart modules

**Status:** pending
**Epic:** visualization
**Priority:** medium
**Depends on:** none

## Description

`visualization/base/views.js` is 1,072 lines — the largest file in the
codebase (Python or JS). It handles crosshair tooltips, trade box
management, S/R line rendering, timeline markers, and chart lifecycle in
one monolith. This is backlog 078's scope extended to cover the full file.

Split into:

- **`views/crosshair.js`** (~250 lines) — `_onCrosshairMove`,
  `_hitAnnotationTooltip`, `_showTooltip`, `_showTradeTooltip`,
  tooltip positioning/hiding
- **`views/trades.js`** (~200 lines) — `TradeBoxPrimitive`,
  `_tradeBoxesAt`, `_hitTradeBox`, trade box show/hide/reposition
- **`views/markers.js`** (~150 lines) — `setMarkers` assembly (trades,
  swings, signals, rejections), marker color/shape logic
- **`views/overlays.js`** (~200 lines) — EMA series, zigzag lines,
  S/R price lines, `updateSR`, `_srHits`
- **`views/chart.js`** (~150 lines) — chart lifecycle (`build`/`destroy`/`resize`),
  series setup, panel management (ATR, volume)
- **`views.js`** (~120 lines) — thin `ChartView` facade composing the above

## Design

1. Each module exports a mixin or set of functions that `ChartView` calls.
2. `views.js` becomes the composition root — creates chart, mixes in
   behaviors, exposes public API.
3. `interactive.py` `_BASE_MODULE_NAMES` extended with new filenames in
   dependency order: `chart`, `overlays`, `markers`, `trades`, `crosshair`,
   `views`.
4. Concatenation pipeline unchanged — new files are concatenated before
   `views.js`.
5. All JS tests pass without modification (they test `ChartView` public API,
   not internal file structure).

## Acceptance Criteria

- [ ] `views.js` <150 lines (thin facade)
- [ ] Each new module <250 lines
- [ ] `_BASE_MODULE_NAMES` lists all new files in dependency order
- [ ] `node --check` on concatenated output clean
- [ ] All 51 JS tests pass unchanged
- [ ] `eslint` + `prettier` clean on new files
- [ ] Rendered HTML byte-equivalent (no behavior change)

## Related

- `src/marketatlas/visualization/base/views.js` (1,072 lines, primary target)
- `src/marketatlas/visualization/interactive.py:252-254` (`_BASE_MODULE_NAMES`)
- Backlog 078 — original partial scope (now superseded by this)
