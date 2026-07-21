# Pullback Pattern Detector

**Epic:** mvp

## Problem

No pattern detection exists. The MVP's primary pattern is pullback — detecting when price retraces within a trend.

## Goal

`PullbackDetector` consumes `TrendFact` + `ATRFact` + `MarketView` to produce `PullbackFact`. Detects retracement depth and status.

## Design

### 1. PullbackDetector

File: `src/marketatlas/analysis/patterns/pullback.py`

```python
class PullbackDetector(Analyzer):
    def __init__(self, min_retracement_atr: float = 0.5, max_retracement_atr: float = 2.0): ...

    def requires(self) -> tuple[type[Fact], ...]:
        return (TrendFact, ATRFact)

    def produces(self) -> tuple[type[Fact], ...]:
        return (PullbackFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult: ...
```

### 2. Pullback Detection Logic

In a bullish trend:
- Find recent swing low (lowest low since last swing high)
- Measure distance from swing high to current price
- Retracement = (swing_high - current) / (swing_high - swing_low)
- Express retracement in ATR units: `retracement_atr = retracement_distance / atr`

Status determination:
- `DETECTED`: Retracement exceeds `min_retracement_atr` but hasn't reached potential support
- `CONFIRMED`: Retracement within target zone AND price shows reversal candle (e.g., bullish engulfing, hammer)
- `INVALIDATED`: Retracement exceeds `max_retracement_atr` (trend may be broken)

### 3. Swing Detection (Simplified)

For MVP, use simple swing detection:
- Swing high: candle where high > previous high AND high > next high
- Swing low: candle where low < previous low AND low < next low
- Only look back `window_size` candles

### 4. Evidence

- `"Pullback DETECTED in bullish trend"`
- `"Retracement: 1.2 ATR from swing high 51000"`
- `"Current price 49800, swing low 49200"`
- `"Waiting for reversal confirmation"`

### 5. Tests

- Bullish trend + price retraces 1.0 ATR → PullbackStatus.DETECTED
- Bullish trend + price retraces 0.2 ATR → no pullback (below threshold)
- Bullish trend + price retraces 2.5 ATR → PullbackStatus.INVALIDATED
- Evidence describes the pullback context

## Evidence

- `PullbackDetector().analyze(view, {TrendFact: trend, ATRFact: atr}).facts[0].status == PullbackStatus.DETECTED`
- Evidence explains why pullback was detected
