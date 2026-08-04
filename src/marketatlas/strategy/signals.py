from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.types import Timeframe
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
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> TradeSignal | None: ...

    @staticmethod
    def _fact_key(key: str) -> FactKey:
        """Resolve a fact-key string to a ``FactKey`` (backlog 062).

        A ``name@timeframe`` suffix (as emitted by the compiler for
        cross-timeframe signal ``requires``) carries an explicit timeframe; a
        bare name resolves without one, matching pre-timeframe behaviour.
        """
        if "@" in key:
            name, tf = key.rsplit("@", 1)
            return FactKey(name, timeframe=Timeframe(tf))
        return FactKey(key)
