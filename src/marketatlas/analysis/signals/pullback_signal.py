from marketatlas.analysis.factkey import FactKey
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.strategy.signals import Signal, TradeSignal, resolve_fact_key


def _pullback_strength(pattern: tuple[float, ...]) -> float:
    """Retracement depth of the second leg relative to the first.

    The swing pattern is a low/high/low/high (bullish) or
    high/low/high/low (bearish) price sequence; the pullback strength is how
    far price retraced on the third point before the pattern resumed. An empty
    or incomplete pattern scores 0.
    """
    if len(pattern) < 3:
        return 0.0
    a, b, c = pattern[0], pattern[1], pattern[2]
    leg = abs(b - a)
    if leg <= 0:
        return 0.0
    return abs(c - b) / leg


class PullbackSignal(Signal):
    def __init__(
        self,
        min_strength: float = 0.5,
        pullback_key: str = "pullback_pattern",
        trend_key: str = "trend",
        atr_key: str = "atr_14",
    ) -> None:
        self._min_strength = min_strength
        self._pullback_key = pullback_key
        self._trend_key = trend_key
        self._atr_key = atr_key

    def requires(self) -> tuple[FactKey, ...]:
        return (FactKey("pullback_pattern"), FactKey("trend"), FactKey("atr_14"))

    def evaluate(self, view: MarketView, facts: dict[FactKey, Fact]) -> TradeSignal | None:
        pullback_key = resolve_fact_key(facts, self._pullback_key)
        trend_key = resolve_fact_key(facts, self._trend_key)
        atr_key = resolve_fact_key(facts, self._atr_key)

        pullback = facts.get(pullback_key) if pullback_key is not None else None
        trend = facts.get(trend_key) if trend_key is not None else None
        atr = facts.get(atr_key) if atr_key is not None else None

        if not isinstance(pullback, PullbackFact):
            return None
        if not isinstance(trend, TrendFact):
            return None
        if not isinstance(atr, ATRFact):
            return None

        if pullback.direction == TrendDirection.NEUTRAL:
            rejections = (
                EvidenceEntry(
                    text="Rejected: pullback direction is neutral",
                    level=EvidenceLevel.WARNING,
                    source="PullbackSignal",
                ),
            )
            return self._rejected_signal(rejections)

        strength = (
            pullback.strength
            if pullback.strength is not None
            else _pullback_strength(pullback.swing_pattern)
        )
        if strength < self._min_strength:
            rejections = (
                EvidenceEntry(
                    text=(
                        f"Rejected: pullback strength {strength:.2f} "
                        f"< min {self._min_strength:.2f}"
                    ),
                    level=EvidenceLevel.WARNING,
                    source="PullbackSignal",
                ),
            )
            return self._rejected_signal(rejections)

        current = view.current
        atr_val = atr.value if atr.value > 0 else 0.0
        buffer = 0.5 * atr_val

        entry_zone = (current.close - buffer, current.close + buffer)

        confidence = strength * trend.strength

        evidence = (
            EvidenceEntry(
                text=(
                    f"Signal: {pullback.direction.value} pullback detected, "
                    f"strength {strength:.2f}, confidence {confidence:.2f}"
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

    def _rejected_signal(
        self, rejections: tuple[EvidenceEntry, ...]
    ) -> TradeSignal:
        return TradeSignal(
            direction=TrendDirection.NEUTRAL,
            entry_zone=(0.0, 0.0),
            confidence=0.0,
            source="PullbackSignal",
            evidence=(),
            rejections=rejections,
        )
