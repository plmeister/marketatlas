from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from marketatlas.facts.base import Fact


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class TrendFact(Fact):
    direction: TrendDirection
    strength: float  # 0.0-1.0


class SwingType(Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class SwingPoint:
    price: float
    index: int
    type: SwingType
    timestamp: datetime


@dataclass(frozen=True)
class SwingFact(Fact):
    swings: tuple[SwingPoint, ...]


@dataclass(frozen=True)
class SRLevel:
    price: float
    strength: int
    type: str  # "support" or "resistance"


@dataclass(frozen=True)
class SRFact(Fact):
    levels: tuple[SRLevel, ...]


@dataclass(frozen=True)
class SwingStructureFact(Fact):
    points: tuple[SwingPoint, ...]


@dataclass(frozen=True)
class RangePositionFact(Fact):
    """Where a reference price sits inside a completed higher-timeframe range.

    ``position`` is ``0.0`` at the range low and ``1.0`` at the range high, and
    may fall outside that interval when the price has broken beyond the last
    completed bar's extremes. ``None`` when no higher-timeframe bar has completed
    yet, in which case no filter decision can be made.
    """

    high: float
    low: float
    position: float | None
