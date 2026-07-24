# Support/Resistance Analyzer

**Epic:** strategy

## Problem

No support/resistance fact exists. Trade sizing needs S/R levels to avoid placing trades where price must cross a level (higher reversal probability). Stop placement also needs nearest S/R.

## Goal

`SupportResistanceAnalyzer` consumes `SwingFact` to identify S/R levels from clustered swing points. Produces `SRFact` containing levels with strength and type.

## Design

### 1. SRFact

File: `src/marketatlas/facts/structural.py` (extend)

```python
@dataclass(frozen=True)
class SRLevel:
    price: float
    strength: int         # number of touches (swings at this level)
    type: str             # "support" or "resistance"

@dataclass(frozen=True)
class SRFact(Fact):
    levels: tuple[SRLevel, ...]  # sorted by price
```

### 2. SupportResistanceAnalyzer

File: `src/marketatlas/analysis/analyzers/sr.py`

```python
class SupportResistanceAnalyzer(Analyzer):
    def __init__(
        self,
        swing_key: str = "swing",
        atr_key: str = "atr_14",
        level_tolerance_atr: float = 0.5,
    ): ...
```

Detection logic:
- Read `SwingFact.swings`
- Cluster swing points that are within `level_tolerance_atr × ATR` of each other
- Each cluster becomes an S/R level
- `strength` = number of swings in cluster
- Classify: level below current price → support, above → resistance
- Sort by price

### 3. Read-Ahead Safety

- Only uses `SwingFact` (computed from past data) and current price
- No future data access

### 4. Evidence

- `"Identified 4 S/R levels: 2 support (48200×3, 49100×2), 2 resistance (51500×2, 52800×1)"`
- `"Nearest support: 49100 (2 touches), nearest resistance: 51500 (2 touches)"`

### 5. Tests

- Multiple swing clusters → correct levels with correct strength
- Single swing → strength 1
- No swings → empty levels
- Levels correctly classified as support vs resistance based on current price

## Evidence

- SRFact contains correctly clustered and classified levels
- Strength counts are accurate
