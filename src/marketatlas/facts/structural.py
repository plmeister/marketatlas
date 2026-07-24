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
