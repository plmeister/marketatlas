from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping
from datetime import datetime
from typing import overload

from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class MarketStore:
    """Immutable collection of candles, indexable by position or timestamp.

    Candle timestamps are expected sorted ascending per timeframe (the
    contract DataStore/resample already uphold).
    """

    @overload
    def __init__(self, data: MarketData) -> None: ...
    @overload
    def __init__(self, data: Mapping[Timeframe, MarketData]) -> None: ...

    def __init__(self, data: MarketData | Mapping[Timeframe, MarketData]) -> None:
        if isinstance(data, MarketData):
            data = {data.timeframe: data}
        self._data: dict[Timeframe, MarketData] = dict(data)
        self._primary_tf = min(
            self._data.keys(),
            key=lambda tf: _tf_minutes(tf),
        )

    def __len__(self) -> int:
        return len(self._data[self._primary_tf].candles)

    def __getitem__(self, index: int) -> Candle:
        return self._data[self._primary_tf].candles[index]

    def slice(self, start: int, end: int) -> tuple[Candle, ...]:
        return self._data[self._primary_tf].candles[start:end]

    @property
    def symbol(self) -> Symbol:
        return self._data[self._primary_tf].symbol

    @property
    def timeframe(self) -> Timeframe:
        return self._primary_tf

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        return tuple(c.timestamp for c in self._data[self._primary_tf].candles)

    @property
    def available_timeframes(self) -> tuple[Timeframe, ...]:
        return tuple(sorted(self._data.keys(), key=lambda tf: _tf_minutes(tf)))

    def get_candles(self, timeframe: Timeframe) -> tuple[Candle, ...]:
        md = self._data.get(timeframe)
        if md is None:
            return ()
        return md.candles

    def __contains__(self, timeframe: Timeframe) -> bool:
        return timeframe in self._data

    def _candles(self, timeframe: Timeframe | None) -> tuple[Candle, ...]:
        tf = timeframe if timeframe is not None else self._primary_tf
        if tf not in self._data:
            raise ValueError(f"No data available for timeframe {tf}")
        return self._data[tf].candles

    def _timestamps(self, timeframe: Timeframe | None) -> tuple[datetime, ...]:
        return tuple(c.timestamp for c in self._candles(timeframe))

    def timestamp_index(self, timestamp: datetime, timeframe: Timeframe | None = None) -> int:
        """Index of the latest candle at-or-before ``timestamp``; -1 if none.

        O(log n) binary search over the timeframe's sorted timestamps.
        """
        timestamps = self._timestamps(timeframe)
        if not timestamps:
            return -1
        return bisect_right(timestamps, timestamp) - 1

    def in_range(
        self,
        start: datetime,
        end: datetime,
        timeframe: Timeframe | None = None,
    ) -> tuple[Candle, ...]:
        """Candles with ``start <= timestamp <= end`` (inclusive), in order."""
        timestamps = self._timestamps(timeframe)
        if not timestamps:
            return ()
        lo = bisect_left(timestamps, start)
        hi = bisect_right(timestamps, end)
        return self._candles(timeframe)[lo:hi]


_TF_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
    Timeframe.W1: 10080,
}


def _tf_minutes(tf: Timeframe) -> int:
    return _TF_MINUTES[tf]
