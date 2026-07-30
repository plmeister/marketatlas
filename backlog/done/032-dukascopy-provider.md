# 032: Dukascopy Data Provider

**Status:** pending  
**Epic:** data  
**Priority:** high

## Description

Add Dukascopy as alternative data provider. Better forex/CFD data than Yahoo. Dukascopy offers free tick data via JForex API or S3 CSV downloads.

## Acceptance Criteria

- [ ] `DukascopyProvider` implements `DataProvider` interface
- [ ] Downloads candle data from Dukascopy S3 (public CSV format)
- [ ] Supports major timeframes: 1m, 5m, 15m, 1h, 4h, 1d
- [ ] Handles Dukascopy symbol format (e.g. `EURUSD`, `GBPJPY`)
- [ ] Returns data in same `Candle` format as YahooProvider
- [ ] Caches downloaded data locally (avoid re-fetching)
- [ ] Error handling: network failures, invalid symbols, rate limits
- [ ] Unit tests with mock HTTP responses

## Technical Notes

- Dukascopy public data: `https://datafeed.dukascopy.com/datafeed/{instrument}/{year}/{month}/{dayohlcv}.{tf}.bi5`
- BI5 format is binary (zlib compressed) — need decompression
- Alternative: use `dukascopy` Python package for simplified access
- Symbol mapping handled by instrument registry (backlog 033)

## Related

- `src/marketatlas/data/providers/yahoo.py` — existing provider
- `src/marketatlas/data/providers/base.py` — DataProvider interface
- Backlog 033: Instrument registry
