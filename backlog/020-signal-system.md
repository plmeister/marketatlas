# Signal System

**Epic:** strategy

## Problem

No signal layer exists. After analyzers produce facts, nothing evaluates them to produce trade signals. Need a `Signal` base class and a `PullbackSignal` implementation that reads analyzer outputs and decides whether a trade opportunity exists.

## Goal

Signals consume facts from the analysis graph and produce `TradeSignal` objects — lightweight descriptors of direction, entry zone, and confidence. The risk layer (021) consumes these to compute actual trades.

## Design

### 1. TradeSignal

File: `src/marketatlas/strategy/signals.py`

```python
@dataclass(frozen=True)
class TradeSignal:
    direction: TrendDirection   # BULLISH / BEARISH
    entry_zone: tuple[float, float]  # (low, high) acceptable entry range
    confidence: float           # 0.0–1.0
    source: str                 # which signal produced this
    evidence: tuple[EvidenceEntry, ...]
```

### 2. Signal Base

```python
class Signal(ABC):
    @abstractmethod
    def evaluate(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> TradeSignal | None:
        """Return TradeSignal if opportunity exists, None otherwise."""
```

### 3. PullbackSignal

File: `src/marketatlas/analysis/signals/pullback_signal.py`

```python
class PullbackSignal(Signal):
    def __init__(
        self,
        min_strength: float = 0.5,
        pullback_key: str = "four_swing_pullback",
        trend_key: str = "trend",
    ): ...
```

Logic:
- Read `PullbackFact` from facts
- If `status == CONFIRMED` and `confirmation_strength >= min_strength`:
  - Entry zone = `[current.close, current.close ± 0.5 × ATR]` (small buffer around current price)
  - Confidence = `confirmation_strength × trend.strength`
  - Return `TradeSignal`
- Otherwise return `None`

### 4. Strategy Integration

Signals are instantiated from config like analyzers:

```python
class Strategy:
    def __init__(self, config: StrategyConfig): ...
    def build_graph(self) -> AnalysisGraph: ...
    def build_signals(self) -> list[Signal]: ...
    def evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> list[TradeSignal]: ...
```

### 5. Read-Ahead Safety

- Signal reads only `facts` dict (computed from current frame)
- No cross-frame state
- Entry zone is based on `view.current` — the candle being evaluated

### 6. Evidence

- `"Signal: bullish pullback confirmed, confidence 0.72"`
- `"Entry zone: 52900–53400"`

### 7. Tests

- Confirmed pullback with strong trend → TradeSignal returned
- Detected but not confirmed → None
- Invalidated pullback → None
- Entry zone is reasonable relative to current price
- Confidence reflects both pullback and trend quality

## Evidence

- PullbackSignal correctly evaluates PullbackFact status
- Returns None when conditions not met
- Entry zone and confidence are sensible
