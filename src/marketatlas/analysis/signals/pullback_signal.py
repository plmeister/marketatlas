from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.strategy.signals import Signal, TradeSignal


class PullbackSignal(Signal):
    def __init__(
        self,
        min_strength: float = 0.5,
        pullback_key: str = "four_swing_pullback",
        trend_key: str = "trend",
        atr_key: str = "atr_14",
    ) -> None:
        self._min_strength = min_strength
        self._pullback_key = pullback_key
        self._trend_key = trend_key
        self._atr_key = atr_key

    def evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> TradeSignal | None:
        pullback = facts.get(self._fact_key(self._pullback_key))
        trend = facts.get(self._fact_key(self._trend_key))
        atr = facts.get(self._fact_key(self._atr_key))

        if not isinstance(pullback, PullbackFact):
            return None
        if not isinstance(trend, TrendFact):
            return None
        if not isinstance(atr, ATRFact):
            return None

        if pullback.status != PullbackStatus.CONFIRMED:
            return None
        if pullback.confirmation_strength < self._min_strength:
            return None
        if pullback.direction == TrendDirection.NEUTRAL:
            return None

        current = view.current
        atr_val = atr.value if atr.value > 0 else 0.0
        buffer = 0.5 * atr_val

        if pullback.direction == TrendDirection.BULLISH:
            entry_zone = (current.close - buffer, current.close + buffer)
        else:
            entry_zone = (current.close - buffer, current.close + buffer)

        confidence = pullback.confirmation_strength * trend.strength

        evidence = (
            EvidenceEntry(
                text=(
                    f"Signal: {pullback.direction.value} pullback confirmed, "
                    f"confidence {confidence:.2f}"
                ),
                level=EvidenceLevel.SIGNAL,
                source="PullbackSignal",
            ),
            EvidenceEntry(
                text=(f"Entry zone: {entry_zone[0]:.0f}\u2013{entry_zone[1]:.0f}"),
                level=EvidenceLevel.INFO,
                source="PullbackSignal",
            ),
        )

        return TradeSignal(
            direction=pullback.direction,
            entry_zone=entry_zone,
            confidence=round(confidence, 4),
            source="PullbackSignal",
            evidence=evidence,
        )
