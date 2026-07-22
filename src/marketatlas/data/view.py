from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle


@dataclass(frozen=True)
class MarketView:
    store: MarketStore
    cursor: int
    window_size: int = 100

    @property
    def current(self) -> Candle:
        return self.store[self.cursor]

    @property
    def history(self) -> tuple[Candle, ...]:
        start = max(0, self.cursor - self.window_size)
        return self.store.slice(start, self.cursor)

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
        return 0 <= self.cursor < len(self.store) and self.cursor >= self.window_size
