from datetime import datetime

from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


class MarketStore:
    def __init__(self, data: MarketData) -> None:
        self._candles = data.candles
        self._symbol = data.symbol
        self._timeframe = data.timeframe
        self._timestamps = tuple(c.timestamp for c in self._candles)

    def __len__(self) -> int:
        return len(self._candles)

    def __getitem__(self, index: int) -> Candle:
        return self._candles[index]

    def slice(self, start: int, end: int) -> tuple[Candle, ...]:
        return self._candles[start:end]

    @property
    def symbol(self) -> Symbol:
        return self._symbol

    @property
    def timeframe(self) -> Timeframe:
        return self._timeframe

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        return self._timestamps
