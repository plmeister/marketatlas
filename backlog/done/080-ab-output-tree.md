# 080: A/B output tree — split charts by choice combination

**Status:** pending
**Epic:** portfolio
**Priority:** high
**Depends on:** 079

## Description

The single-symbol `--ab` path currently writes one chart per variant with
ordinal names (`ab_result_v1.html`, `ab_result_v2.html`). Ordinals are opaque:
`v2` does not say which choice values it ran. For comparisons to be easy the
output tree must be keyed by the **choice combination** itself.

Replace ordinal names with deterministic, filesystem-safe slugs derived from a
variant's differing parameters (e.g. `min_strength=0.5` → `ms050`;
`max_stop_atr: <3 | 5>` × `min_strength: <0.3 | 0.5>` → `ms050_atr3`,
`ms050_atr5`, …). Same combination always yields the same slug, so runs are
diffable across dates and nothing depends on variant count or order.

Output layout:

- Single-symbol `--ab`: `--output <stem>.html` → `output/<stem>/<slug>/<stem>.html`
  (one dir per variant) — or, when the user keeps the flat path, per-variant
  files named `<stem>.<slug>.html`.
- Portfolio `--ab`: `output/<stem>/<slug>/portfolio.<canonical>.html` per
  instrument, reusing `render_per_instrument_charts` with the variant's
  filtered book.

Slug generation lives in one helper (`variant_slug(template)`) consumed by the
renderer and by the future index page (081); the label from 079 and the slug
must be derived from the same variant-identity logic so they never disagree.

## Acceptance Criteria

- [ ] Slugs are deterministic and stable across runs for an identical choice
      combination; no ordinal indexes appear in output paths
- [ ] Single-symbol `--ab` writes one variant dir per combination with a
      correct slug; existing non-`--ab` `run` output is unchanged
- [ ] Portfolio `--ab` writes per-instrument charts under each variant dir
- [ ] `variant_slug` and the 079 label come from one shared
      variant-identity helper
- [ ] Slugs are filesystem-safe (no `/`, spaces, or characters that break
      `Path`/URLs) and collision-free for distinct combinations
- [ ] Rendering block shared between single and portfolio `--ab` paths (no
      duplicated chart-write code)
- [ ] Tests: slug function unit tests (incl. multi-choice combos, sanitization)
      + CLI test asserting the output tree layout
- [ ] `poetry run lint` green

## Related

- `src/marketatlas/cli.py` — `_run_ab_test` output block (currently
  `_v{i}.html` ordinal naming)
- `src/marketatlas/visualization/portfolio.py` — `render_per_instrument_charts`
- `src/marketatlas/visualization/interactive.py` — `InteractiveRenderer`
