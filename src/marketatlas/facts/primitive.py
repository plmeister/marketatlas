from dataclasses import dataclass
from datetime import datetime

from marketatlas.facts.base import Fact


@dataclass(frozen=True)
class EMAFact(Fact):
    value: float
    period: int


@dataclass(frozen=True)
class SMAFact(Fact):
    value: float
    period: int


@dataclass(frozen=True)
class ATRFact(Fact):
    value: float
    period: int


@dataclass(frozen=True)
class ATRPoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class ATRSeriesFact(Fact):
    """Per-candle ATR history (Wilder smoothing), one point per candle.

    Unlike the scalar ``ATRFact``, the value at each candle is anchored to the
    data available at that candle — causal and immutable as new data arrives.
    """

    points: tuple[ATRPoint, ...]
    period: int


@dataclass(frozen=True)
class RSIFact(Fact):
    value: float
    period: int


@dataclass(frozen=True)
class VolumeFact(Fact):
    avg_volume: float
    period: int
