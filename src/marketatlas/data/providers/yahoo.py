from __future__ import annotations

from datetime import UTC, datetime
from time import sleep

import yfinance as yf  # type: ignore[import-untyped]

from marketatlas.data.instrument import InstrumentRegistry
from marketatlas.data.providers.base import DataProvider, RateLimitError, SymbolNotFoundError
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class YahooProvider(DataProvider):
    _TIMEFRAME_MAP = {
        Timeframe.M1: "1m",
        Timeframe.M5: "5m",
        Timeframe.M15: "15m",
        Timeframe.M30: "30m",
        Timeframe.H1: "1h",
        Timeframe.H4: "1h",  # Yahoo doesn't have 4h, will need resampling
        Timeframe.D1: "1d",
        Timeframe.W1: "1wk",
    }

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        registry: InstrumentRegistry | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._registry = registry

    def _resolve_symbol(self, symbol: Symbol) -> Symbol:
        if self._registry is None:
            return symbol
        yahoo_sym = self._registry.get_symbol(symbol.name, "yahoo")
        if yahoo_sym is not None:
            return Symbol(yahoo_sym)
        return symbol

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        interval = self._TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        resolved = self._resolve_symbol(symbol)
        ticker = yf.Ticker(resolved.name)

        for attempt in range(self._max_retries):
            try:
                df = ticker.history(
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=False,
                )
                break
            except Exception as e:
                if "Too Many Requests" in str(e) or "429" in str(e):
                    if attempt < self._max_retries - 1:
                        sleep(self._retry_delay * (attempt + 1))
                        continue
                    raise RateLimitError(f"Rate limited after {self._max_retries} attempts") from e
                raise

        if df.empty:
            raise SymbolNotFoundError(symbol)

        candles = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            candles.append(
                Candle(
                    timestamp=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )

        return MarketData(symbol=symbol, timeframe=timeframe, candles=tuple(candles))

    def supported_symbols(self) -> list[Symbol]:
        return []
