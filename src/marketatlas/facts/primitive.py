from dataclasses import dataclass

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
class RSIFact(Fact):
    value: float
    period: int


@dataclass(frozen=True)
class VolumeFact(Fact):
    avg_volume: float
    period: int
