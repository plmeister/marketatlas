from dataclasses import dataclass
from enum import Enum

from marketatlas.facts.base import Fact
from marketatlas.facts.structural import TrendDirection


class PullbackStatus(Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class PullbackFact(Fact):
    status: PullbackStatus
    retracement_atr: float
    direction: TrendDirection
    swing_pattern: tuple[float, ...] = ()
    deviation_pct: float = 0.0
    confirmation_strength: float = 0.0
