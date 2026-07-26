# 026: Separate JS Template for HTML Renderer

**Status:** pending  
**Priority:** high

## Description

Extract JavaScript from inline HTML string into a separate `.js` template file. Current approach embeds 3MB+ of JS/JSON directly in HTML string in Python code — impossible to lint, test, or validate.

## Acceptance Criteria

- [ ] JS lives in `src/marketatlas/visualization/template.js` (or similar)
- [ ] Python renderer reads template file and injects data (CANDLES, FRAMES, etc.) via string replacement or simple templating
- [ ] Template has placeholders like `{{CANDLES}}`, `{{FRAMES}}`, `{{EMA_SERIES}}`, etc.
- [ ] JS file can be validated with `node --check` independently
- [ ] HTML output identical to current output (no behavioral change)
- [ ] No external template dependencies (no Jinja, no npm) — pure string replace

## Technical Notes

- Current bug: missing `}` in `createPriceLine` call (line 126 of generated JS) — syntax error breaks entire chart
- Separate file makes this catchable via lint/syntax check
- Keep template simple: one JS file, placeholders for data arrays

## Related

- `src/marketatlas/visualization/interactive.py` — current renderer
- Bug: `missing ) after argument list` at line 126 of generated JS
