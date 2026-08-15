# 082: A/B index page controls — interactive choice selector

**Status:** pending
**Epic:** portfolio
**Priority:** low
**Depends on:** 081

## Description

The "controls" option for the portfolio A/B index: extend the static 081 page
with vanilla-JS controls so the user can select values per choice dimension and
see that combination's performance without scrolling past every table.

Behaviour:

- One control per choice dimension (e.g. a segmented control or `<select>` for
  `min_strength`, one for `max_stop_atr`, …). Selecting values filters the
  summary grid and detail sections down to the matching combination.
- Variant summaries are embedded once as JSON (from the same data the 081
  tables were built from) and rendered by JS; no per-variant markup duplication.
- **Progressive enhancement**: with JS disabled the page degrades to the full
  081 static tables — the JSON is the only addition, tables are still server-
  rendered.
- The JS mirrors the existing embedded script style used by the interactive
  renderer (`InteractiveRenderer` inline `<script>`, no framework). Size is
  kept small — the codebase has no bundler, so a single hand-written block.

## Acceptance Criteria

- [ ] One control per choice dimension; selecting a value shows only the
      matching combination's grid row + detail sections
- [ ] Default state shows the full static view (identical to 081 page)
- [ ] With JS disabled, the page still shows every combination's tables
      (tables are server-rendered, JSON is additive)
- [ ] Variant data embedded as a single JSON object; no duplicated per-variant
      HTML under each control state
- [ ] Script is inline, dependency-free, and mirrors the existing
      `InteractiveRenderer` style
- [ ] Tests: data-serialization unit test (JSON matches server-rendered
      numbers); manual/JS smoke check documented in the backlog PR
- [ ] `poetry run lint` green

## Related

- `src/marketatlas/visualization/portfolio.py` — `_INDEX_TEMPLATE` (page shell)
- `src/marketatlas/visualization/interactive.py` — existing inline-script
  pattern to mirror
- `backlog/081-ab-comparison-index.md` — the static page this enhances
