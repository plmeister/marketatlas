# 103 — Review notebook (ipynb) with tagged feedback cells

**Epic:** strategy

## Context

The manual-review loop (095/096/097) works: render snapshot PNGs, annotate
`.txt` sidecars beside each PNG, and `marketatlas review` joins notes to the
run's POIs. But the two artifacts (PNGs scattered in a dir + free-text `.txt`
files) are clumsy for a human:

- Charts are not embedded anywhere; the reviewer jumps between an image
  viewer and text files.
- Feedback is detached from the chart, so context is lost mid-review.
- There is no single navigable document that ties a run together.

A Jupyter notebook is a natural fit: charts embed natively, each setup can get
its own markdown feedback cell right below its chart, and the whole run becomes
one self-contained review artifact that an agent can also parse.

A spike is already implemented in `src/marketatlas/review/notebook.py`
(`marketatlas review --notebook out.ipynb`) — this backlog formalizes it.

## Scope

Provide `marketatlas review --notebook out.ipynb` that writes a self-contained
ipynb (nbformat v4) review document, and a reader that extracts tagged
feedback cells back into the existing review-bundle pipeline.

## Cell contract

Each POI section is three cells:

```
[markdown] header  -- basename, kind, symbol, ts, outcome
[code    ] chart   -- embedded image/png output (base64, self-contained)
[markdown] review  -- first line:  <!-- REVIEW: <basename> -->
```

- Flagship: `marketatlas review --snapshots DIR --output-json X --notebook out.ipynb`
  embeds every snapshot PNG under `DIR` (base64, so the notebook is portable
  without the PNGs), plus a tagged review cell per POI.
- Existing `.txt` sidecar verdicts are prefilled into their review cells so the
  notebook preserves previously recorded feedback.
- `iter_review_cells(notebook) -> {basename: feedback}` extracts review-cell
  bodies back out; the `<!-- REVIEW: <basename> -->` tag maps each to a POI via
  `snapshot_basename`, keeping the same-basename join the `.txt` sidecars give.
- Feedback flows into the same `ContextBundle` shape as 097 so the agentic
  tuning step is unchanged.
- Notebook is written even when zero notes exist (the user starts typing from
  a blank tagged cell), unlike the `.txt`-only path that early-returns.
- Empty/placeholder review cells ("reviewed, no action") are treated as "no
  note" — they do not spawn bundles.

## Requirements

- [x] `review --notebook PATH` CLI flag writes the self-contained ipynb
      (implemented in `src/marketatlas/review/notebook.py`).
- [x] Embed charts as base64 `image/png` notebook outputs (no external PNG
      path dependency once written).
- [x] Header cell shows the POI summary (kind/symbol/ts/outcome = same fields
      `format_bundle` shows for each kind: trade entry/stop/target/result/pnl,
      rejection reason, pattern name).
- [x] Prefill review cells from existing `.txt` sidecars; blank otherwise.
- [x] `iter_review_cells` extracts tagged cells into `{basename: text}` and the
      notebook reader feeds them into `iter_review`'s bundle construction.
- [x] Feedback extraction loop: `review --notebook EXISTING.ipynb` reads tagged
      cells back (does not overwrite) and passes them as `extra_notes` to
      `iter_review`, where notebook feedback wins over a stale `.txt` sidecar.
- [x] Integration: `review --notebook X --json Y` writes both the notebook and
      the machine-report so the agentic path is unchanged.
- [x] Reading a notebook never rewrites a human's wording (same guarantee as
      096).

## Testing

- [x] `tests/test_review_notebook.py` (spike, tier1): schema (nbformat 4,
      embedded `image/png` output), tagged cells, empty-vs-content
      discrimination, round-trip write→read, intro placeholder not matched.
- [x] `tests/test_review.py` `extra_notes` cases: notebook feedback overrides a
      stale `.txt` sidecar; notebook note supplies a bundle without a sidecar;
      notebook basename with no PNG is reported as an orphan.
- [ ] Do **not** mark the notebook as a replacement for `--snapshots DIR` PNGs;
      the PNG files remain the source of truth for rendering.

Depends on: 095, 096, 097.
Unblocks: agent-driven feedback->tuning loop (consumes extracted bundles).