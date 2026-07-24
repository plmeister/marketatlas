from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.base import Fact
from marketatlas.facts.structural import TrendDirection


@dataclass(frozen=True)
class TradeSignal:
    direction: TrendDirection
    entry_zone: tuple[float, float]
    confidence: float
    source: str
    evidence: tuple[EvidenceEntry, ...]


class Signal(ABC):
    @abstractmethod
    def evaluate(
        self, view: MarketView, facts: dict[tuple[type[Fact], str], Fact]
    ) -> TradeSignal | None: ...
