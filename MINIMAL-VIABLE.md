# Market Analysis Engine — Minimum Viable Product Specification

## 1. Purpose

Build a minimal but extensible market analysis system capable of:

- Loading historical market data.
- Replaying market history candle-by-candle.
- Computing market facts.
- Detecting a trading pattern.
- Producing explainable analysis output.
- Visualising the state of the market at any historical point.

The MVP should establish the core architecture required for future expansion without introducing unnecessary complexity.

---

# 2. Core Design Principles

## Immutable Market State

Historical market data is never modified.

The system advances through time by moving a cursor over the data.

```
MarketStore
      |
      v
MarketView(cursor=N)
```

Changing the cursor changes what the system can see.

---

## Analysis Produces Knowledge

Analysis components do not directly produce trades.

They produce facts and explanations.

Every analysis step returns:

```
AnalysisResult

- Fact
- Evidence
- Metadata
```

---

## No DataFrame Leakage

DataFrames are allowed internally in the data layer.

They must not appear in analysis code.

Analysis consumes domain objects:

```
MarketView
```

not:

```
DataFrame
```

---

# 3. System Components

```
Parquet Files
      |
      v
MarketRepository
      |
      v
MarketStore
      |
      v
MarketView
      |
      v
Analysis Engine
      |
      v
Analysis Frames
      |
      v
Strategy Evaluation
```

---

# 4. Data Layer

## MarketRepository

Responsibilities:

- Load OHLCV data.
- Provide symbol/timeframe access.
- Hide storage implementation.

Initial implementation:

- Local Parquet files.

Future implementations:

- Database.
- Remote providers.
- Live feeds.

---

## MarketStore

Immutable collection of market data.

Contains:

```
Symbol
Timeframe
Timestamp index
OHLCV series
```

---

## MarketView

Represents the market state visible at a point in time.

Example:

```
MarketView

current_index = 500

window = previous 100 candles
```

Provides:

```
current candle

historical window

price series

volume series
```

---

# 5. Analysis Layer

## Analyzer Interface

Every analyzer follows:

```
Input:
    MarketView
    Required Facts

Output:
    AnalysisResult
```

Example:

```
EMA Analyzer

requires:
    Close Prices

produces:
    EMA Fact
```

---

# 6. Facts

Facts are immutable observations.

Initial MVP facts:

## EMA Fact

Contains:

- EMA value.
- Period.

---

## ATR Fact

Contains:

- ATR value.
- Period.

---

## Trend Fact

Derived from:

- EMA20.
- EMA50.
- ATR.

Contains:

```
direction

strength
```

---

# 7. Pattern Detection

Initial pattern:

## Pullback Pattern

Inputs:

```
TrendFact

ATRFact

MarketView
```

Produces:

```
PullbackFact
```

Example:

```
Trend:
    bullish

Retracement:
    1.2 ATR

Status:
    active
```

---

# 8. Analysis Frame

Every candle processed creates an immutable frame.

```
AnalysisFrame

timestamp

facts

evidence

annotations

diagnostics
```

Example:

```
2026-01-15

Trend:
    Bullish

Pullback:
    Detected

Evidence:
    Price touched EMA20

Annotation:
    Pullback start marker
```

---

# 9. Evidence Model

Every fact may provide human-readable context.

Examples:

```
EMA20 crossed EMA50

ADX exceeded threshold

Price retraced 1.5 ATR

Trend confirmed by higher highs
```

Evidence must be stored with the frame.

---

# 10. Visualisation Output

MVP output:

Static HTML report.

Contains:

- Price chart.
- Candles.
- Indicators.
- Entry/exit markers.
- Evidence annotations.

The renderer consumes:

```
AnalysisFrame
```

It does not execute analysis.

---

# 11. Backtesting

Backtesting is simply replay:

```
for candle in MarketStore:

    create MarketView

    execute analyzers

    store AnalysisFrame
```

The strategy evaluates frames.

---

# 12. Explicitly Out of Scope

MVP does not include:

- Live trading.
- Multiple symbols.
- Portfolio management.
- Automatic optimisation.
- Multiple swing algorithms.
- Machine learning.
- Broker integration.

The architecture must allow these later.
