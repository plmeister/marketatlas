# ATR Analyzer

**Epic:** mvp

## Problem

No volatility measurement exists. ATR (Average True Range) is critical for pullback detection and risk assessment.

## Goal

`ATRAnalyzer` computes ATR from candle data. Configurable period. Produces `ATRFact`.

## Design

### 1. ATRAnalyzer

File: `src/marketatlas/analysis/analyzers/atr.py`

```python
class ATRAnalyzer(Analyzer):
    def __init__(self, period: int = 14): ...

    def requires(self) -> tuple[type[Fact], ...]:
        return ()

    def produces(self) -> tuple[type[Fact], ...]:
        return (ATRFact,)

    def analyze(self, view: MarketView, facts: dict[type[Fact], Fact]) -> AnalysisResult: ...
```

### 2. ATR Calculation

True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
ATR = SMA of True Range over `period` candles (or Wilder's smoothing)

### 3. Evidence

- `"ATR14 = 1234.56"`
- `"ATR represents 2.4% of price"`

### 4. Tests

- Known ATR values from manual calculation
- Period=14 on 100 candles produces correct final ATR
- First candle has no TR (needs previous close)
- Evidence is descriptive

## Evidence

- `ATRAnalyzer(14).analyze(view, {}).facts[0].value` matches expected ATR
- Evidence describes volatility context
