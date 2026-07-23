# External Market Data Fetcher

**Epic:** mvp

## Problem

No way to get real market data into the system. Parquet loading (002) assumes data already exists locally. Need a way to fetch OHLCV candle data from external providers and persist as Parquet.

## Goal

`DataProvider` abstraction with implementations for Yahoo Finance and Dukascopy. Fetch OHLCV data for a symbol/timeframe, convert to `MarketData`, save as Parquet.

## Design

### 1. DataProvider Interface

File: `src/marketatlas/data/providers/base.py`

```python
class DataProvider(ABC):
    @abstractmethod
    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData: ...

    @abstractmethod
    def supported_symbols(self) -> list[Symbol]: ...
```

### 2. Yahoo Finance Provider

File: `src/marketatlas/data/providers/yahoo.py`

- Uses `yfinance` library
- Maps `Timeframe` to Yahoo interval strings (`1h`, `1d`, etc.)
- Returns OHLCV as `MarketData`
- Handles rate limiting and retry

### 3. Dukascopy Provider

File: `src/marketatlas/data/providers/dukascopy.py`

- Uses `dukascopy` Python library
- Fetches tick data and resamples to requested timeframe
- Good for forex/instruments not on Yahoo
- Handles timezone conversion

### 4. CLI Command

File: `src/marketatlas/cli.py`

```
marketatlas fetch --symbol BTCUSDT --timeframe 1h --start 2024-01-01 --end 2024-12-31 --provider yahoo --output data/
```

- Fetches data from provider
- Saves as `{symbol}.{timeframe}.parquet` in output dir
- Shows progress bar

### 5. Fallback Chain

```python
class ProviderChain(DataProvider):
    def __init__(self, providers: list[DataProvider]): ...

    def fetch(self, symbol, timeframe, start, end) -> MarketData:
        for provider in providers:
            try:
                return provider.fetch(symbol, timeframe, start, end)
            except (SymbolNotFoundError, RateLimitError):
                continue
        raise NoDataAvailableError(symbol, timeframe)
```

### 6. Tests

- Mock provider returns known data
- ProviderChain falls back to next provider on error
- CLI command creates Parquet file
- Round-trip: fetch → save → load matches

## Evidence

- `YahooProvider().fetch(Symbol("BTCUSDT"), Timeframe.H1, start, end)` returns `MarketData`
- `marketatlas fetch --symbol BTCUSDT --provider yahoo` creates parquet file
- ProviderChain handles provider failures gracefully
