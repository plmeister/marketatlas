# Fact Type System

**Epic:** mvp

## Problem

Analysis results need a typed, immutable structure. Need a base `Fact` type and initial fact types for EMA, ATR, and Trend.

## Goal

Core fact types defined as frozen dataclasses. Each fact carries its computed values plus evidence of how it was derived.

## Design

### 1. Base Fact

File: `src/marketatlas/facts/base.py`

```python
@dataclass(frozen=True)
class Fact:
    timestamp: datetime
    evidence: tuple[str, ...] = ()
```

### 2. Primitive Facts

File: `src/marketatlas/facts/primitive.py`

```python
@dataclass(frozen=True)
class EMAFact(Fact):
    value: float
    period: int

@dataclass(frozen=True)
class SMAFact(Fact):
    value: float
    period: int

@dataclass(frozen=True)
class ATRFact(Fact):
    value: float
    period: int

@dataclass(frozen=True)
class RSIFact(Fact):
    value: float
    period: int

@dataclass(frozen=True)
class VolumeFact(Fact):
    avg_volume: float
    period: int
```

### 3. Structural Facts

File: `src/marketatlas/facts/structural.py`

```python
class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

@dataclass(frozen=True)
class TrendFact(Fact):
    direction: TrendDirection
    strength: float  # 0.0-1.0
```

### 4. Pattern Facts

File: `src/marketatlas/facts/pattern.py`

```python
class PullbackStatus(Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"

@dataclass(frozen=True)
class PullbackFact(Fact):
    status: PullbackStatus
    retracement_atr: float
    direction: TrendDirection
```

### 5. Tests

- All facts are frozen (attempting mutation raises FrozenInstanceError)
- Facts carry evidence tuples
- Enum values match expected strings

## Evidence

- `EMAFact(timestamp=..., value=50000.0, period=20)` is frozen
- `TrendFact(..., direction=TrendDirection.BULLISH, strength=0.8).direction == TrendDirection.BULLISH`
