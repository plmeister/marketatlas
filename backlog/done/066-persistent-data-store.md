# 066: Persistent Market Data Store

**Status:** pending  
**Epic:** data  
**Priority:** medium

## Description

Persistent local store for fetched market data so repeated runs fetch only what's missing: 50 backtests over the same instruments/timeframes → 1 network fetch, 49 served from disk. Keyed by `(instrument, timeframe, date range)` with coverage metadata that answers "do I have X from A to B?" before any fetch is attempted.

Today caching is piecemeal: DukascopyProvider caches per-day raw BI5 files (dukascopy.py:61,107-153), and the CLI fetch path (cli.py:100-132) re-fetches per run. No unified store, no coverage query, no range-awareness.

## Scope

- `DataStore`: local persistent storage keyed `(instrument, timeframe)`, values are candles (Parquet — matches MarketStore round-trip) or raw files (keep both? decide)
- Coverage API: `has(instrument, timeframe, start, end) -> bool` (or partial-coverage ranges) — the primary query for 065-driven fetches
- `get(instrument, timeframe, start, end)` / `put(...)`; store returns cached data on overlap, missing ranges on gap
- Fetch flow: caller computes `required_data` (065), queries store, fetches only uncovered ranges, writes back
- Store lives outside source tree (configurable path, e.g. `~/.cache/marketatlas/`); survives across runs
- Optionally migrate/absorb Dukascopy's existing cache format (compat read) — decide, keep Dukascopy working either way

## Non-Goals

- No data-provider logic (Yahoo/Dukascopy keep fetch responsibility)
- No graph/AST coupling (consumes 065 output only)
- No multi-run dedup of analysis results — data only

## Acceptance Criteria

- [ ] Store serves cached candles across process restarts (persistence proven)
- [ ] `has`/coverage query answers range subsumption correctly (partial overlap detected, gaps reported)
- [ ] 50 identical backtests → 1 fetch (integration test with a stub provider)
- [ ] Instrument × timeframe isolation: no cross-contamination
- [ ] Configurable store path; sane defaults
- [ ] CLI backtest flow uses 065 + store before fetching
- [ ] Tests: coverage logic (unit), persistence (process-restart), fetch-missing-only (integration), legacy Dukascopy cache compat if adopted

## Technical Notes

- Parquet for candles aligns with `MarketStore` round-trip (WORKLOG 012) and the data layer's existing format.
- Store must be concurrency-safe enough for the CLI; keep it simple (per-symbol-tf files, no DB).

## Related

- Backlog 065 (requirements inference — feeds coverage query)
- Backlogs 046 (multi-TF fetch), 003 (Parquet loading), 012 (frame storage)
- `src/marketatlas/data/providers/dukascopy.py`, `src/marketatlas/cli.py`
