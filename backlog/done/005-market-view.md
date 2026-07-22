# MarketView — Cursor-Based Window

**Epic:** mvp

## Problem

Analysis code needs a bounded view of the market at a point in time, not the entire dataset. Need a cursor-based view that moves through time.

## Goal

`MarketView` represents the market state visible at a specific candle index. Provides current candle, historical window, and price/volume series.

## Design

### 1. MarketView

File: `src/marketatlas/data/view.py`

```python
@dataclass(frozen=True)
class MarketView:
    store: MarketStore
    cursor: int
    window_size: int = 100

    @property
    def current(self) -> Candle: ...

    @property
    def history(self) -> tuple[Candle, ...]: ...

    @property
    def prices(self) -> tuple[float, ...]: ...

    @property
    def volumes(self) -> tuple[float, ...]: ...

    @property
    def highs(self) -> tuple[float, ...]: ...

    @property
    def lows(self) -> tuple[float, ...]: ...

    @property
    def timestamps(self) -> tuple[datetime, ...]: ...

    @property
    def index(self) -> int: ...

    @property
    def is_valid(self) -> bool: ...
```

### 2. Behavior

- `current` = candle at cursor position
- `history` = previous `window_size` candles (excluding current)
- All series derived from history + current
- `is_valid` = cursor within valid range and enough history

### 3. Tests

- View with cursor=50 shows candle 50 as current
- History contains candles 0..49 (with window_size=50)
- Prices tuple matches close prices
- View with cursor=0 has empty history
- View with cursor beyond store length is invalid

## Evidence

- `MarketView(store, cursor=50).current == store[50]`
- `len(MarketView(store, cursor=50, window_size=100).history) == 50`
