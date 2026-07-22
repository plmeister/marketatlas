# Trend Analyzer

**Epic:** mvp

## Problem

No trend detection exists. Need to determine market direction and strength from EMA relationship and price action.

## Goal

`TrendAnalyzer` consumes `EMAFact` (EMA20 + EMA50) and `ATRFact` to produce `TrendFact` with direction and strength.

## Design

### 1. TrendAnalyzer

File: `src/marketatlas/analysis/analyzers/trend.py`

```python
class TrendAnalyzer(Analyzer):
    def __init__(self, fast_period: int = 20, slow_period: int = 50): ...

    def requires(self) -> tuple[type[Fact], ...]:
        return (EMAFact,)  # needs both EMA20 and EMA50

    def produces(self) -> tuple[type[Fact], ...]:
        return (TrendFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult: ...
```

### 2. Trend Logic

- Requires two EMA facts (fast + slow) in the facts dict
- If fast EMA > slow EMA → bullish
- If fast EMA < slow EMA → bearish
- Strength based on:
  - EMA spread relative to ATR (normalized)
  - Price position relative to EMAs
  - Slope of EMA spread over recent candles

### 3. Evidence

- `"Trend: Bullish — EMA20 (50234) > EMA50 (49800)"`
- `"Strength: 0.72 — spread 434 = 0.35 ATR"`
- `"Confirmed by price above both EMAs"`

### 4. Tests

- EMA20 > EMA50 → TrendDirection.BULLISH
- EMA20 < EMA50 → TrendDirection.BEARISH
- EMA20 == EMA50 → TrendDirection.NEUTRAL
- Strength scales with EMA spread
- Evidence describes reasoning

## Evidence

- `TrendAnalyzer().analyze(view, {EMAFact: ema20, ATRFact: atr}).facts[0].direction == TrendDirection.BULLISH`
- Evidence tuple contains trend description
