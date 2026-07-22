from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Timeframe(Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Symbol:
    name: str


@dataclass(frozen=True)
class MarketData:
    symbol: Symbol
    timeframe: Timeframe
    candles: tuple[Candle, ...]
