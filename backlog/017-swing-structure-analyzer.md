# Swing Structure Analyzer

**Epic:** strategy

## Problem

Swing point detection is ad-hoc inside `PullbackDetector`. Need a dedicated, reusable analyzer that identifies swing highs and swing lows with configurable parameters, producing a `SwingFact` that other analyzers (pullback, S/R) consume.

## Goal

`SwingStructureAnalyzer` scans the MarketView window, identifies all qualifying swing highs and swing lows, and produces a `SwingFact` containing the ordered list of swing points. Reusable by pullback detector and S/R analyzer.

## Design

### 1. SwingPoint Data

File: `src/marketatlas/facts/structural.py` (extend)

```python
class SwingType(Enum):
    HIGH = "high"
    LOW = "low"

@dataclass(frozen=True)
class SwingPoint:
    price: float
    index: int           # index within the MarketView window
    type: SwingType
    timestamp: datetime

@dataclass(frozen=True)
class SwingFact(Fact):
    swings: tuple[SwingPoint, ...]  # ordered by index, oldest first
```

### 2. SwingStructureAnalyzer

File: `src/marketatlas/analysis/analyzers/swing.py`

```python
class SwingStructureAnalyzer(Analyzer):
    def __init__(
        self,
        lookback: int = 20,
        min_swing_atr: float = 0.3,
        atr_key: str = "atr_14",
    ): ...
```

Detection logic:
- Scan candles in window
- A swing high is a candle whose `high` exceeds both neighbors
- A swing low is a candle whose `low` is below both neighbors
- Filter: swing must move at least `min_swing_atr` × ATR from previous swing of same type
- Result: ordered list of alternating swing points (no two consecutive highs or lows — keep the more extreme)

### 3. Read-Ahead Safety

- Swing detection only sees `view.history + (view.current,)` — never future candles
- ATR is read from the facts dict (already computed from past data)
- Swing index is relative to the window, not the full store

### 4. Evidence

- `"Detected 7 swing points in window (4 highs, 3 lows)"`
- `"Filtered 2 swings below minimum 0.3 ATR separation"`
- `"Swing range: 48200.00 to 52100.00"`

### 5. Tests

- Clean uptrend: produces alternating H/L/H/L pattern
- Flat/sideways: few or no qualifying swings
- Filter removes swings too close together
- Evidence describes detection results
- Window with <3 candles: returns empty swings

## Evidence

- `SwingStructureAnalyzer().analyze(view, facts).facts[0]` is `SwingFact` with ordered swings
- No future data visible to analyzer
