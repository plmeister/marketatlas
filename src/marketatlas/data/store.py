from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import overload

from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class MarketStore:
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
