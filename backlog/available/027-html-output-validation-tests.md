# 027: HTML Output Validation Tests

**Status:** pending  
**Priority:** high

## Description

Test suite that validates generated HTML is syntactically correct and functionally complete. Catches bugs like missing braces, broken JS, empty data arrays.

## Acceptance Criteria

- [ ] Test: generated HTML contains valid JS (parse with `node --check` or equivalent)
- [ ] Test: all expected data constants exist (CANDLES, FRAMES, TRADES, EMA_SERIES, ATR_DATA, SR_DATA, etc.)
- [ ] Test: FRAMES.length > 0 when backtest runs on non-trivial data
- [ ] Test: HTML contains expected DOM elements (chart-container, frame-controls, info-panel, etc.)
- [ ] Test: JS syntax valid — no missing braces/parens
- [ ] Test: `updateFrame(0)` callable without error (basic smoke test)
- [ ] Use `BeautifulSoup` or regex for HTML structure checks
- [ ] Use `node --check` subprocess for JS validation

## Technical Notes

- Depends on backlog 026 (separate JS template) for reliable JS validation
- Can start with basic HTML structure + JS syntax tests before template split
- Store test fixtures: small candle dataset (10 candles), expected output snapshot

## Related

- `tests/test_interactive_renderer.py` — existing tests (no HTML validation)
- `src/marketatlas/visualization/interactive.py` — renderer
