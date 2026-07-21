# Market Analysis Engine — Architecture Roadmap and Evolution Guide

## 1. Vision

The system evolves from a backtesting tool into an explainable market analysis platform.

The core output is not trades.

The core output is:

```
A historical record of everything the system knew about the market at each point in time.
```

Strategies, visualisation, optimisation and execution become consumers of this knowledge.

---

# 2. Long-Term Architecture

```
                 Market Providers
                       |
                       v
              Market Synchronisation
                       |
                       v
              Canonical Market Store
                       |
                       v
                  Market Views
                       |
                       v
              Analysis Dependency Graph
                       |
                       v
              Market Knowledge Frames
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
   Strategies    Visualisation   Research Tools
        |
        v
   Risk Management
        |
        v
   Execution
```

---

# 3. Analysis Dependency Graph

The analysis engine should not contain a fixed pipeline.

Each analyzer declares:

```
Requires:

Produces:
```

Example:

```
TrendAnalyzer

requires:

EMA20Fact
EMA50Fact
SwingFact
ADXFact

produces:

TrendFact
```

The engine builds the execution graph automatically.

---

# 4. Fact Architecture

Facts are grouped into layers.

## Primitive Facts

Direct calculations.

Examples:

- EMA.
- SMA.
- ATR.
- RSI.
- ADX.
- VWAP.
- Volume statistics.

---

## Structural Facts

Interpret market behaviour.

Examples:

- Swing structure.
- Higher highs/lower lows.
- Trend.
- Market regime.
- Support/resistance.

---

## Pattern Facts

Describe opportunities.

Examples:

- Pullback.
- Breakout.
- Reversal.
- Consolidation.
- Continuation.

---

## Evaluation Facts

Assess opportunities.

Examples:

- Trade quality.
- Available reward.
- Risk.
- Confidence.

---

# 5. Swing Architecture

Swing detection is an interchangeable analysis model.

Interface:

```
SwingAnalyzer
```

Implementations:

```
FractalSwingAnalyzer

ZigZagSwingAnalyzer

ATRSwingAnalyzer
```

All produce:

```
SwingFact
```

Containing:

- Swing points.
- Strength.
- Confirmation state.
- Market structure information.

---

# 6. Support and Resistance

Support/resistance becomes a fact source.

Possible analyzers:

```
SwingLevelAnalyzer

PivotAnalyzer

VolumeProfileAnalyzer

VWAPAnalyzer

PreviousHighLowAnalyzer
```

Outputs:

```
SupportResistanceFact
```

Containing:

- Levels.
- Strength.
- Source.
- Confidence.
- Evidence.

---

# 7. Evidence and Explainability

Every analysis result contains:

```
Fact

Evidence

Annotations

Metadata
```

Evidence explains:

```
Why was this fact produced?
```

Annotations explain:

```
How should this appear visually?
```

Metadata explains:

```
How was this calculated?
```

---

# 8. Market Knowledge Frames

The central persisted object becomes:

```
MarketKnowledgeFrame

timestamp

market state

facts

patterns

evidence

annotations

diagnostics
```

A complete backtest produces:

```
Frame 1
Frame 2
Frame 3
...
Frame N
```

---

# 9. Replay Model

Replay should never recalculate.

The system:

```
Load Analysis History

Move cursor

Render frame
```

A user moving a time slider should instantly see:

- Indicators.
- Patterns.
- Support/resistance.
- Trade decisions.
- Explanations.

Exactly as they existed at that point.

---

# 10. Visualisation Architecture

Visualisation consumes frames.

Possible renderers:

```
TradingView Renderer

HTML Renderer

JSON Export

Console Renderer
```

The analysis engine has no dependency on the UI.

---

# 11. Strategy Architecture

Strategies become thin consumers.

Example:

```
Pullback Strategy

requires:

TrendFact

PullbackFact

TradeSpaceFact

RiskFact

produces:

TradeCandidate
```

Strategies should not calculate indicators.

---

# 12. Risk Engine

Risk becomes an independent layer.

Inputs:

```
TradeCandidate

ATR

SupportResistance

TradeSpace

Volatility
```

Outputs:

```
TradeProposal

Entry

Stop

Target

Position Size

Expected Risk/Reward
```

---

# 13. Data Evolution

Initial:

```
Parquet
```

Later:

```
Parquet
    |
DuckDB
    |
Time-series database
```

The repository abstraction hides this.

---

# 14. Live Trading Evolution

Historical:

```
HistoricalMarketView
```

Live:

```
LiveMarketView
```

Both implement:

```
MarketView
```

The analysis engine remains unchanged.

---

# 15. Future Research Capabilities

Because every frame is persisted:

- Strategy comparison.
- Walk-forward analysis.
- Parameter optimisation.
- Explainable AI models.
- Pattern discovery.
- Market regime analysis.

become queries over historical knowledge rather than repeated recalculation.

---

# 16. Guiding Principle

The system should be designed as:

```
Raw Market Data

        ↓

Market Understanding

        ↓

Decision Making
```

not:

```
Strategy Code

        ↓

Indicators

        ↓

Trades
```

The analysis engine is the product. Strategies are consumers of it.
