# 065: Data Requirements Inference

**Status:** pending  
**Epic:** ast  
**Priority:** high

## Description

Derive, before execution, exactly which market data is needed: walk the template graph and compute the set of `(instrument, timeframe)` pairs required for a run, given the runtime instrument list (063) and node timeframes (061). Group nodes (064) consume facts and add no direct fetches — the union of member instruments' timeframes covers them. Date range is included so the caller can check coverage (066).

This is the interface between the graph and the data layer: backtest/CLI call `required_data(...)` first, then fetch only what's missing.

## Scope

- `required_data(instruments, start, end) -> set[tuple[Instrument, Timeframe]]` on the template graph (or concrete AST)
- Walk node scope × declared timeframe; per-instrument scope → (instrument, tf) per instrument; group scope → no direct entries, but union members' instrument-scope sets
- `Analysis.required_timeframes() -> set[Timeframe]` for the AST side (before instruments known)
- Dedup identical entries; deterministic ordering for stable output
- Date range carried for 066 coverage checks (not for fetch set cardinality)

## Non-Goals

- No fetching or caching (backlog 066)
- No network/provider logic

## Acceptance Criteria

- [ ] Single instrument, single TF → one pair
- [ ] Multi-TF graph (trend@1d + swings@1w) → both TFs per instrument
- [ ] Multi-instrument run → N × TFs, deduped
- [ ] Group node contributes no direct entries; union over group members correct
- [ ] Empty graph / no instruments → empty set (or error, per 063)
- [ ] CLI/backtest consumes it: fetch happens only for `required_data` gaps (integration with 066)
- [ ] Tests: each scope/TF combination, dedup, determinism, group union

## Technical Notes

- Keep this a pure function of template graph + runtime inputs — no I/O, trivially testable.
- The set feeds 066's store as a "coverage query", not as a fetch mandate.

## Related

- Backlogs 061 (node timeframes), 063 (instrument scope), 064 (group union) — prereqs
- Backlog 066 (persistent store consumes this), 046 (multi-TF fetching today)
- `src/marketatlas/analysis/ast/`, `src/marketatlas/cli.py`
