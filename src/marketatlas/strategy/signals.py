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


@dataclass(frozen=True)
class SignalEvaluation:
    """Outcome of running a ``Signal``.

    Carries either a real, actionable ``TradeSignal`` or the rejection reasons
    the signal produced. Rejection reasons live here (the evaluation), never
    on ``TradeSignal``, so a signal object does not double as a rejection
    carrier.
    """

    signal: TradeSignal | None = None
    rejections: tuple[EvidenceEntry, ...] = ()

    @property
    def is_signal(self) -> bool:
        return self.signal is not None


class Signal(ABC):
    @abstractmethod
    def requires(self) -> tuple[FactKey, ...]: ...

    def produces(self) -> tuple[FactKey, ...]:
        return ()

    @abstractmethod
    def evaluate(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> TradeSignal | None: ...

    def evaluate_with_rejections(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> SignalEvaluation:
        """Single-pass evaluation including rejection reasons.

        The default delegates to :meth:`evaluate`; signals that need to
        surface *why* they declined may override both to run one shared pass.
        """
        return SignalEvaluation(signal=self.evaluate(view, facts))

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


def resolve_fact_key(facts: dict[FactKey, Fact], key: str) -> FactKey | None:
    """Resolve a fact-key string against available facts.

    An exact key wins. A bare name falls back to the first available fact with
    that name regardless of its timeframe, so signals/risk nodes work against
    DSL-compiled strategies whose analyzers always carry a timeframe (facts are
    keyed ``name@tf``). Returns ``None`` when nothing matches.
    """
    exact = Signal._fact_key(key)
    if exact in facts:
        return exact
    for fk in facts:
        if fk.name == exact.name:
            return fk
    return None
