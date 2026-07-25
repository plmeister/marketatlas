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
- **015** — HTML visualization: HTMLRenderer produces self-contained HTML with TradingView lightweight-charts. Candlestick chart, EMA overlays, ATR panel, pullback markers, evidence on crosshair move. 17 tests. 185 total.
- **002** — External data fetcher: DataProvider interface, YahooProvider with yfinance, ProviderChain for fallback, CLI command. 7 tests. 192 total.
- **016** — Strategy config loader: YAML→StrategyConfig with AnalyzerConfig/SignalConfig/RiskConfig. Analyzer registry, validation, build_analyzers. 21 tests. 213 total.
- **017** — Swing structure analyzer: SwingStructureAnalyzer detects swing highs/lows from MarketView. SwingFact with ordered alternating swings, ATR-based separation filter, configurable lookback. 18 tests. 231 total.
- **018** — Four-swing pullback detector: FourSwingPullbackDetector consumes SwingFact+TrendFact+ATRFact, validates HH/HL/HH/HL and LL/LH/LL/LH patterns, linearity filter, confirmation candle check. Enhanced PullbackFact with swing_pattern, deviation_pct, confirmation_strength. 30 tests. 261 total.
- **019** — S/R analyzer: SupportResistanceAnalyzer consumes SwingFact+ATRFact, clusters swings within ATR tolerance, classifies as support/resistance by current price. SRFact with levels sorted by price, strength as touch count. 15 tests. 276 total. **Registry fix**: Added SupportResistanceAnalyzer to ANALYZER_TYPES in loader.py.
- **020** — Signal system: TradeSignal dataclass, Signal ABC, PullbackSignal evaluates PullbackFact+TrendFact+ATRFact for entry signals. Strategy class builds graph+signals from config, evaluates at each frame. 23 tests. 299 total.
- **021** — Risk layer: RiskEngine consumes TradeSignal+ATRFact+SwingFact+SRFact to produce TradeCandidate with entry (slippage-adjusted), stop (swing-based), target (RR-based), position size (balance × risk_pct). S/R crossing rejection, max stop distance clamp, configurable RR range. TradeCandidate dataclass. 22 tests. 321 total.
- **022** — Strategy-aware backtester: TradeBook tracks trades with P&L, win/loss, drawdown. StrategyBundle merges multiple strategy graphs with dedup. Backtester integrates signals+risk engine, fills orders at next open, resolves stop/target. 17 tests. 325 total.
- **023** — No-readahead audit: 12 regression tests proving no future data leakage. Frame independence, MarketView boundary, analyzer/signal/risk isolation, TradeBook resolution (fill at N+1 open), full backtest determinism, single-trade constraint. Fixed StrategyBundle._merge_graphs sorting bug. 12 tests. 337 total.
