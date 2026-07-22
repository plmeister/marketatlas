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
