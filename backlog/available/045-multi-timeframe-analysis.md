# 045: Multi-Timeframe Analysis

**Status:** pending
**Epic:** data
**Priority:** medium

## Description

Enable analyzers to operate on different timeframes within a single strategy. For example, swing detection and SR levels computed on weekly data, with those facts available to pullback detectors and signal generators working on daily resolution.

Currently all analyzers share a single `MarketView` at one resolution. Multi-timeframe requires: per-analyzer timeframe configuration, fetching multiple data streams from provider, cross-timeframe fact routing, and execution ordering that respects timeframe dependencies.

## Acceptance Criteria

- [ ] `MarketStore` supports multiple timeframe data streams — can hold or reference candles at different resolutions
- [ ] Provider layer fetches data at requested resolution(s) natively; resampling is fallback only
- [ ] Resampling/aggregation module converts higher-resolution candles to lower-resolution (1d→1w, 1h→4h, etc.) when provider doesn't support target TF
- [ ] AST / strategy config allows specifying `timeframe` per analyzer definition (default: strategy base timeframe)
- [ ] `MarketView` or equivalent is parameterized by timeframe; analyzers receive a view at their configured resolution
- [ ] Facts are tagged with their source timeframe (`FactKey` includes or is paired with timeframe)
- [ ] Execution engine (graph compiler) handles multi-timeframe DAG: analyzer A on TF1 depends on fact B from analyzer C on TF2
- [ ] `SupportResistanceAnalyzer` produces stable weekly SR levels irrespective of daily candle additions (major source of current swing instability)
- [ ] At least one end-to-end test: strategy with weekly swing analyzer + daily pullback detector → correct fact propagation

## Technical Notes

- **Fetch first**: if strategy requests weekly data, query provider for weekly candles directly. Only resample from daily if provider has no weekly endpoint.
- Resampling: aggregate higher-resolution candles into lower-resolution using standard OHLCV (Open = first, High = max, Low = min, Close = last, Volume = sum)
- Data store may hold multiple timeframes as separate internal series, or a single store with a resampling adapter layer
- Timeframe key design: `FactKey` could become `(name: str, params: frozenset, timeframe: str)` or timeframe is appended to the key string (e.g. `swing_1w`)
- Execution order: graph traversal must respect both fact dependencies and timeframe resolution (higher TF runs first since it covers more history per tick)
- This enables the "S/R levels drawn on weekly chart" use case which is inherently more stable than daily S/R

## Related

- `src/marketatlas/analysis/analyzers/swing.py` — swing detection (would gain `timeframe` param)
- `src/marketatlas/analysis/analyzers/sr.py` — support/resistance (primary beneficiary)
- `src/marketatlas/data/types.py` — `Timeframe` enum
- `src/marketatlas/data/store.py` — `MarketStore` (needs multi-TF support)
- `src/marketatlas/data/providers/` — provider interface (may need multi-TF fetch)
- `src/marketatlas/analysis/` — base analyzer classes, graph compiler
- `src/marketatlas/strategy/` — strategy config loader
