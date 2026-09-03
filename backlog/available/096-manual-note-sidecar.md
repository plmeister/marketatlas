# 096 — Manual annotation sidecar notes (`.txt` beside `.png`)

**Epic:** strategy

## Context

Backtest → snapshot images are triage-able (backlog 095). The next human step
is manual review: look at each PNG, form a judgement on the algorithm's
behaviour, and record feedback that a later agent can act on.

Today there is no place to attach a verdict to a snapshot. Filenames are
`SYM_DATE_kind_direction_result_pnlXY.png` (see `snapshot_basename`). We want a
free-text note with a **same-name `.txt``** beside each PNG that the review agent
(backlog 097) and the web UI can read.

## Scope

A note sidecar model + writer helper that pairs a snapshot PNG with a
``<basename>.txt`` (basename shared, extension swapped). Notes are free-form
Markdown and are authored by hand by the human reviewer.

## Workflow / contract

```
output/snapshots/
  EURGBP_2026-03-27_pattern_pullback_pattern.png
  EURGBP_2026-03-27_pattern_pullback_pattern.txt   <- hand-authored
```

- Note = Markdown text, filename = PNG filename with `.png` → `.txt`.
- A missing note file means "not yet reviewed"; an **empty** note means
  "reviewed, no action".
- Note stays manually authored — the system only creates/reads, never rewrites
  a human's wording.

## Requirements

- [ ] `src/marketatlas/visualization/notes.py`:
      - `note_path(png_path: Path) -> Path` (swap extension).
      - `read_note(png_path) -> str | None` (None if no `.txt`, else contents).
      - `iter_notes(snapshots_dir) -> Iterator[tuple[Path, str | None]]`
        yielding (png_path, note_text) pairs.
      - `write_note(png_path, text)` for tests / scaffolding only (create
        empty template when rendering with a new `--notes` flag).
- [ ] Optional `--write-sidecar` (or `--notes` template) flag on snapshot
      rendering so first render also drops an empty `.txt` template per PNG —
      makes the review-ready state visible. Default: off (no filesystem
      noise until reviewer opts in).
- [ ] Note files must never be tracked by git (add `output/snapshots/*.txt`
      to `.gitignore` if not already ignored under `output/`).
- [ ] CLI validation: `snapshot --outdir X` renders PNGs; a `--notes` variant
      writes templates. No note yet for review prompt consumption (that is 097).
- [ ] JSON structured output (`run --output-json`) stays untouched — notes are
      a separate filesystem artifact, not part of the analysis frame.

## Testing

- [ ] `tests/test_notes.py`: extension swap, missing-vs-empty-vs-content
      discrimination, `iter_notes` ordering, template creation idempotency.
- [ ] Notes render alongside snapshots under `--notes`; without the flag no
      `.txt` files appear.

Depends on: 095.
Unblocks: 097.
