# 095 — Snapshot kind filter on CLI

**Epic:** strategy

## Context

Snapshot renderer already supports filtering POIs by kind at the library layer
(`locate_pois(..., kinds=...)` in `visualization/snapshot.py`), and treats each
POI in a typed or JSON output — trades, rejections, patterns (plus sr/swing
geometry). But neither CLI entry point exposes the filter:

- `run --snapshots DIR` calls `render_poi_snapshots(port, out_dir)` with no `kinds`.
- `snapshot JSON --outdir DIR` resolves `render_poi_snapshots` with no `kinds`.

So users cannot triage "only losing trades", "only rejected signals", or "only
pullback patterns". This is a prerequisite for the manual-review loop (backlog
096): reviewers must be able to render a focused subset before annotating.

## Scope

Expose POI-kind filtering as a CLI flag on both `run --snapshots` and the
`snapshot` subcommand, and thread it through to `render_poi_snapshots`.

## Requirements

- [x] Add `--kinds` flag to `snapshot` subparser in `cli/__init__.py`:
      comma-separated list, one of `trade`, `rejection`, `pattern`, `sr`,
      `swing`; also accept the negation form `--kinds !pattern` (exclude).
      Default: all kinds.
- [x] Add same `--kinds` flag to `run --snapshots` path
      (`run_parser` / handled in `commands.py`).
- [x] `_emit_json_and_snapshots` and `snapshot_command` parse `--kinds`
      into a `set[str]` / exclude handling and pass to
      `render_poi_snapshots(...)`.
- [x] Invalid kind name → clear error listing valid kinds, exit non-zero.
- [x] `locate_pois` exclude semantics: support `!x` before/with include
      set (e.g. `--kinds trade,!pattern` = trades minus pattern-tagged, or a
      dedicated `exclude_kinds` param). Document the precedence.
- [x] `--help` text documents the flag (both entry points).

## Testing

- [x] `tests/test_snapshot.py` (or new `tests/test_snapshot_cli.py`):
      render same output with all kinds vs each subset; assert output file
      set (via `snapshot_basename`) matches the filter.
- [x] `--kinds !pattern` produces zero pattern-named files.
- [x] Invalid kind string errors cleanly (subprocess or CLI dispatch).
- [x] `mock.patch` `render_poi_snapshots` to assert `kinds` threads through
      `_emit_json_and_snapshots` and `snapshot_command`.

Depends on: none (existing `locate_pois`).
Unblocks: 096.
