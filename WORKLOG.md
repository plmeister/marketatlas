# Work Log

## Completed

- **001** — Project scaffolding and data model foundation
- **006** — Fact type system: base Fact, primitive facts (EMA/SMA/ATR/RSI/Volume), structural facts (Trend), pattern facts (Pullback). 19 tests passing.
- **003** — Parquet data loading: MarketRepository loads OHLCV from Parquet files into MarketData. Symbol listing, column validation, clear errors. 8 tests.
- **004** — MarketStore: immutable candle collection with O(1) indexed access, slicing, timestamps, symbol/timeframe metadata. 10 tests.
- **005** — MarketView: cursor-based window into MarketStore. Current candle, history window, price/volume/high/low/timestamp series, validity checks. 15 tests.
- **007** — Analyzer interface + graph: Analyzer base class with requires()/produces()/analyze(). AnalysisGraph with topological sort, cyclic dependency detection, unsatisfied dependency detection. 16 tests.
- **008** — EMA analyzer: EMAAnalyzer computes EMA over close prices from MarketView. SMA-seeded, configurable period, bullish/bearish signal evidence. 12 tests.
- **009** — ATR analyzer: ATRAnalyzer computes True Range and ATR from candle data. SMA-seeded with Wilder smoothing, configurable period, pct-of-price evidence. 12 tests.
- **010** — Trend analyzer: TrendAnalyzer computes fast/slow EMA comparison for direction (BULLISH/BEARISH/NEUTRAL) and strength (spread normalized by ATR or price). 15 tests.
- **011** — Pullback detector: PullbackDetector consumes TrendFact + ATRFact to detect retracement within trend. Swing detection with fallback to extremes, ATR-denominated retracement depth, DETECTED/INVALIDATED status. 17 tests.
- **012** — Analysis frame storage: AnalysisFrame (frozen dataclass capturing timestamp, candle, facts, evidence, annotations, diagnostics) and FrameStore (in-memory collection with append/getitem/slice/by_timestamp, Parquet round-trip serialization). 10 tests.
- **013** — Evidence model: EvidenceEntry (text, level, source, annotation_hint), EvidenceLevel enum (INFO/SIGNAL/WARNING), EvidenceCollector (add, entries, by_level, summary). Structured evidence throughout analyzers, facts, and frames. 155 total tests.
- **014** — Backtesting replay loop: Backtester iterates MarketStore, creates MarketView per step, runs AnalysisGraph, stores AnalysisFrame. Progress callback, edge cases (exact window, zero frames). 13 tests. 168 total.
