# Parquet Data Loading — MarketRepository

**Epic:** mvp

## Problem

No way to get market data into the system. Need to load OHLCV data from Parquet files and produce `MarketData` objects.

## Goal

`MarketRepository` loads Parquet files containing OHLCV columns and returns `MarketData` instances. Symbol and timeframe derived from file metadata or path convention.

## Design

### 1. MarketRepository

File: `src/marketatlas/data/repository.py`

```python
class MarketRepository:
    def __init__(self, base_path: Path): ...

    def list_symbols(self) -> list[Symbol]: ...

    def load(self, symbol: Symbol, timeframe: Timeframe) -> MarketData: ...
```

### 2. Parquet Convention

Expected columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`

File naming: `{symbol}.{timeframe}.parquet` (e.g., `BTCUSDT.1h.parquet`)

Directory layout:
```
data/
├── BTCUSDT.1h.parquet
├── BTCUSDT.1d.parquet
└── ETHUSDT.1h.parquet
```

### 3. Implementation

- Use `pyarrow.parquet` or `polars` to read Parquet
- Convert to `tuple[Candle, ...]` for immutability
- Raise clear errors for missing files or malformed data

### 4. Tests

- Create a small test Parquet fixture (10 candles)
- Test load returns correct `MarketData`
- Test missing file raises `FileNotFoundError`
- Test malformed Parquet raises clear error

## Evidence

- `MarketRepository(data_dir).load(Symbol("BTCUSDT"), Timeframe.H1)` returns `MarketData`
- Tests pass with fixture data
