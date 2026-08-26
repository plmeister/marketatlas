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
    _history_cache: tuple[Candle, ...] | None = None
    _prices_cache: tuple[float, ...] | None = None
    _volumes_cache: tuple[float, ...] | None = None
    _highs_cache: tuple[float, ...] | None = None
    _lows_cache: tuple[float, ...] | None = None
    _timestamps_cache: tuple[datetime, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_history_cache", None)
        object.__setattr__(self, "_prices_cache", None)
        object.__setattr__(self, "_volumes_cache", None)
        object.__setattr__(self, "_highs_cache", None)
        object.__setattr__(self, "_lows_cache", None)
        object.__setattr__(self, "_timestamps_cache", None)

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
        cached = object.__getattribute__(self, "_history_cache")
        if cached is not None:
            return cached
        if self.view_timeframe is None:
            start = max(0, self.cursor - self.window_size)
            result = self.store.slice(start, self.cursor)
        else:
            candles = self._series()
            start = max(0, self.cursor - self.window_size)
            result = candles[start : self.cursor]
        object.__setattr__(self, "_history_cache", result)
        return result

    def series_through_cursor(self) -> tuple[Candle, ...]:
        if self.view_timeframe is None:
            return self.store.slice(0, self.cursor)
        return self._series()[: self.cursor]

    @property
    def prices(self) -> tuple[float, ...]:
        cached = object.__getattribute__(self, "_prices_cache")
        if cached is not None:
            return cached
        result = tuple(c.close for c in self.history) + (self.current.close,)
        object.__setattr__(self, "_prices_cache", result)
        return result

    @property
    def volumes(self) -> tuple[float, ...]:
        cached = object.__getattribute__(self, "_volumes_cache")
        if cached is not None:
            return cached
        result = tuple(c.volume for c in self.history) + (self.current.volume,)
        object.__setattr__(self, "_volumes_cache", result)
        return result

    @property
    def highs(self) -> tuple[float, ...]:
        cached = object.__getattribute__(self, "_highs_cache")
        if cached is not None:
            return cached
        result = tuple(c.high for c in self.history) + (self.current.high,)
        object.__setattr__(self, "_highs_cache", result)
        return result

    @property
    def lows(self) -> tuple[float, ...]:
        cached = object.__getattribute__(self, "_lows_cache")
        if cached is not None:
            return cached
        result = tuple(c.low for c in self.history) + (self.current.low,)
        object.__setattr__(self, "_lows_cache", result)
        return result

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        cached = object.__getattribute__(self, "_timestamps_cache")
        if cached is not None:
            return cached
        result = tuple(c.timestamp for c in self.history) + (self.current.timestamp,)
        object.__setattr__(self, "_timestamps_cache", result)
        return result

    @property
    def index(self) -> int:
        return self.cursor

    @property
    def is_valid(self) -> bool:
        return 0 <= self.cursor < self._len() and self.cursor >= self.window_size

    def select(self, timeframe: Timeframe, window_size: int | None = None) -> MarketView:
        if timeframe not in self.store:
            raise ValueError(f"No data available for timeframe {timeframe}")
        current_ts = self.current.timestamp
        new_cursor = self.store.timestamp_index(current_ts, timeframe)
        if new_cursor < 0:
            new_cursor = 0
        ws = window_size if window_size is not None else self.window_size
        return MarketView(self.store, new_cursor, ws, view_timeframe=timeframe)

    def align(self, timestamp: datetime) -> MarketView:
        """View on the same timeframe whose cursor is the latest candle
        at-or-before ``timestamp`` (clamped to the earliest candle)."""
        idx = self.store.timestamp_index(timestamp, self.view_timeframe)
        if idx < 0:
            idx = 0
        return MarketView(self.store, idx, self.window_size, view_timeframe=self.view_timeframe)
