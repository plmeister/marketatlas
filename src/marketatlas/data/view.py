from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, Timeframe


@dataclass(frozen=True)
class MarketView:
    store: MarketStore
    cursor: int
    window_size: int = 100
    view_timeframe: Timeframe | None = None

    def _series(self) -> tuple[Candle, ...]:
        if self.view_timeframe is None:
            return ()
        return self.store.get_candles(self.view_timeframe)

    def _len(self) -> int:
        if self.view_timeframe is None:
            return len(self.store)
        return len(self.store.get_candles(self.view_timeframe))

    @property
    def current(self) -> Candle:
        if self.view_timeframe is None:
            return self.store[self.cursor]
        return self._series()[self.cursor]

    @property
    def history(self) -> tuple[Candle, ...]:
        if self.view_timeframe is None:
            start = max(0, self.cursor - self.window_size)
            return self.store.slice(start, self.cursor)
        candles = self._series()
        start = max(0, self.cursor - self.window_size)
        return candles[start:self.cursor]

    @property
    def prices(self) -> tuple[float, ...]:
        return tuple(c.close for c in self.history) + (self.current.close,)

    @property
    def volumes(self) -> tuple[float, ...]:
        return tuple(c.volume for c in self.history) + (self.current.volume,)

    @property
    def highs(self) -> tuple[float, ...]:
        return tuple(c.high for c in self.history) + (self.current.high,)

    @property
    def lows(self) -> tuple[float, ...]:
        return tuple(c.low for c in self.history) + (self.current.low,)

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        return tuple(c.timestamp for c in self.history) + (self.current.timestamp,)

    @property
    def index(self) -> int:
        return self.cursor

    @property
    def is_valid(self) -> bool:
        return 0 <= self.cursor < self._len() and self.cursor >= self.window_size

    def select(self, timeframe: Timeframe, window_size: int | None = None) -> MarketView:
        candles = self.store.get_candles(timeframe)
        if not candles:
            raise ValueError(f"No data available for timeframe {timeframe}")
        current_ts = self.current.timestamp
        new_cursor = max(
            (i for i, c in enumerate(candles) if c.timestamp <= current_ts),
            default=0,
        )
        ws = window_size if window_size is not None else self.window_size
        return MarketView(self.store, new_cursor, ws, view_timeframe=timeframe)
