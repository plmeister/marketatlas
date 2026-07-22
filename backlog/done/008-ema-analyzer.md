# EMA Analyzer

**Epic:** mvp

## Problem

No indicator computation exists. Need EMA (Exponential Moving Average) as the first primitive analyzer.

## Goal

`EMAAnalyzer` computes EMA over close prices from a `MarketView`. Configurable period. Produces `EMAFact`.

## Design

### 1. EMAAnalyzer

File: `src/marketatlas/analysis/analyzers/ema.py`

```python
class EMAAnalyzer(Analyzer):
    def __init__(self, period: int = 20): ...

    def requires(self) -> tuple[type[Fact], ...]:
        return ()  # only needs close prices from MarketView

    def produces(self) -> tuple[type[Fact], ...]:
        return (EMAFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult: ...
```

### 2. EMA Calculation

Standard EMA formula:
```
EMA_today = close * k + EMA_yesterday * (1 - k)
k = 2 / (period + 1)
```

Seed with SMA of first `period` values.

### 3. Evidence

Produce evidence strings like:
- `"EMA20 = 50234.52"`
- `"EMA20 above price (bearish signal)"` or `"EMA20 below price (bullish signal)"`

### 4. Tests

- Known EMA values from manual calculation
- Period=20 on 100 candles produces correct final EMA
- Evidence tuple is non-empty
- Works with `window_size` smaller than period (returns partial)

## Evidence

- `EMAAnalyzer(20).analyze(view, {}).facts[0].value` matches expected EMA
- Evidence contains human-readable description
