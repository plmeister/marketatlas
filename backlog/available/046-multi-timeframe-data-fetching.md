# 046: Multi-Resolution Data Fetching

**Status:** pending
**Epic:** data
**Priority:** medium

## Description

Data fetching is an independent stage that runs before analysis. The strategy config declares what timeframes are needed. The CLI/provider fetches all required resolutions upfront and stores them in `MarketStore`. Analysis then runs against whatever data is available — missing data causes analyzers to return empty results.

## Acceptance Criteria

- [ ] Strategy config declares required timeframes (derived from analyzer definitions or explicit list)
- [ ] CLI fetch stage requests all required timeframes from provider before analysis starts
- [ ] Provider fetches data at each requested resolution natively when available (e.g. Yahoo weekly endpoint for 1w data)
- [ ] Resampling module converts higher-resolution data to lower-resolution (1d→1w, 1h→4h, etc.) when provider lacks native support for target TF
- [ ] Resampling uses standard OHLCV aggregation: Open = first, High = max, Low = min, Close = last, Volume = sum
- [ ] `MarketStore` stores multiple data series keyed by `Timeframe`
- [ ] Fetch is additive: if store already has data at a resolution, only fetch newer data (incremental)
- [ ] Missing data is not an error — `MarketView` returns empty candles, analyzers handle gracefully
- [ ] CLI shows which timeframes were fetched and which were resampled

## Technical Notes

- **Fetch first**: provider is primary source; resampling is fallback only
- Resampling should handle edge cases: partial weeks, holidays, gaps in source data
- Consider caching resampled output so repeated runs don't re-aggregate
- Not all timeframes need to align to the same date range; fetch each from the same start/end params

## Related

- `src/marketatlas/data/providers/` — provider interface (multi-TF fetch)
- `src/marketatlas/data/store.py` — `MarketStore` (multi-series storage)
- `src/marketatlas/data/types.py` — `Timeframe` enum
- `src/marketatlas/strategy/` — strategy config (required TFs)
- `src/marketatlas/cli.py` — CLI fetch command / pre-analysis stage
- Backlog 045: Multi-resolution MarketView
