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
    direction: TrendDirection
    swing_pattern: tuple[float, ...] = ()
    strength: float | None = None
