from dataclasses import dataclass
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
