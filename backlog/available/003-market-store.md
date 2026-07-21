# MarketStore — Immutable Candle Collection

**Epic:** mvp

## Problem

`MarketData` is just a data holder. Need a store that provides efficient indexed access to candles for building `MarketView` windows.

## Goal

`MarketStore` wraps `MarketData` and provides indexed access, length, and slicing for windowed views.

## Design

### 1. MarketStore

File: `src/marketatlas/data/store.py`

```python
class MarketStore:
    def __init__(self, data: MarketData): ...

    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> Candle: ...

    def slice(self, start: int, end: int) -> tuple[Candle, ...]: ...

    @property
    def symbol(self) -> Symbol: ...

    @property
    def timeframe(self) -> Timeframe: ...

    @property
    def timestamps(self) -> tuple[datetime, ...]: ...
```

### 2. Design Constraints

- Store is immutable after construction
- No DataFrame leakage — only `Candle` objects exposed
- O(1) indexed access via internal tuple storage

### 3. Tests

- Construct from `MarketData`
- `len(store)` returns candle count
- `store[i]` returns correct `Candle`
- `store.slice(0, 10)` returns first 10 candles
- Store exposes symbol and timeframe

## Evidence

- `MarketStore(market_data)[0]` returns first candle
- `len(MarketStore(market_data))` matches candle count
