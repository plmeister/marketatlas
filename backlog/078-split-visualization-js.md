# 078: Split visualization JS into smaller modules

**Status:** pending
**Epic:** visualization
**Priority:** medium
**Depends on:** none

## Description

The visualization JS keeps growing and `views.js` (948 lines) is too large for
an agent to hold in context in one read. Split the chart code into
smaller single-responsibility modules while preserving the existing
concatenation + placeholder pipeline so the rendered HTML is byte-equivalent.

- **`views.js`** → split into:
  - `charts.js` — chart lifecycle (`build`/`destroy`/`resize`), series setup, panels (ATR, volume)
  - `tradeboxes.js` — `TradeBoxPrimitive`, `_tradeBoxesAt`, `_hitTradeBox`, tooltip show/hide
  - `markers.js` — marker assembly (`setMarkers` inputs: trades, swings, signals)
  - `overlays.js` — EMA series, zigzag, S/R price lines, `updateSR`
  - `views.js` — `ChartView` facade that composes the above (thin)
- **`interactive.py`**: extend `_BASE_MODULE_NAMES` with the new module names in dependency order; concatenation and `@data:` placeholder replacement must stay unchanged.
- **`tests/js/views.test.js`**: keep passing unmodified where possible; the split is pure file reorganization — no behavior change, no renames of `ChartView` members.
- `models.js` (285) / `controllers.js` (207) / `interactive.js` (233) are fine as-is; only split when they exceed ~400 lines.

## Acceptance Criteria

- [ ] `_BASE_MODULE_NAMES` lists all new files in dependency order; rendered HTML `node --check` clean
- [ ] All JS tests pass unchanged; no test-only references to file layout introduced
- [ ] `poetry run lint` green (eslint + prettier apply to new files)
- [ ] `views.js` shrinks to a thin facade (<200 lines); each new module <400 lines

## Related

- `src/marketatlas/visualization/interactive.py:252-254` (`_JS_BASE_DIR`/`_BASE_MODULE_NAMES`)
- `src/marketatlas/visualization/base/views.js` (948 lines, primary target)
